import argparse
import asyncio
import json
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
from output.delivery_health import build_weekly_delivery_health, format_weekly_delivery_health
from output.generate_insight import OUTPUT_DIR as INSIGHT_OUTPUT_DIR
from output.generate_insight import generate_insight
from output.map_project_insights import run_project_mapping
from output.signal_report import format_signal_report
from output.generate_study_plan import OUTPUT_DIR as STUDY_PLAN_OUTPUT_DIR
from output.generate_study_plan import generate_study_plan, send_study_reminder
from output.mvp_weekly_pipeline import run_mvp_weekly_pipeline
from output.opportunity_seed_export import export_opportunity_seeds
from processing.cleanup import run_cleanup
from processing.cluster import cluster_posts
from processing.detect_topics import run_topic_detection
from processing.normalize_posts import run_normalization
from processing.score_posts import score_posts


LOGGER = logging.getLogger(__name__)


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return parsed


def _handle_sigterm(_: int, __) -> None:
    LOGGER.info("SIGTERM received, shutting down")
    sys.exit(0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Telegram Research Agent CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap_parser = subparsers.add_parser("bootstrap")
    bootstrap_parser.add_argument("--days", type=_positive_int, default=90, help="Lookback window in days (default: 90)")
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

    seed_parser = subparsers.add_parser(
        "export-opportunity-seeds",
        help="Export recent Telegram demand signals for Demand-to-MVP Radar",
    )
    seed_parser.add_argument("--days", type=int, default=7)
    seed_parser.add_argument("--limit", type=int, default=80)
    seed_parser.add_argument("--out", default=None)
    seed_parser.add_argument("--include-channel", action="append", default=[])
    seed_parser.set_defaults(handler=handle_export_opportunity_seeds)

    live_index_parser = subparsers.add_parser(
        "live-source-index",
        help="Build a bounded live source intelligence snapshot from source events",
    )
    live_index_parser.add_argument("--days", type=int, default=14)
    live_index_parser.add_argument("--event-root", default=None)
    live_index_parser.add_argument("--out", default=None)
    live_index_parser.add_argument(
        "--backfill-from-db",
        action="store_true",
        help="Backfill source events from recent raw_posts before building the snapshot",
    )
    live_index_parser.set_defaults(handler=handle_live_source_index)

    knowledge_extract_parser = subparsers.add_parser(
        "knowledge-extract",
        help="Extract structured Knowledge Atoms from recent Telegram posts",
    )
    knowledge_extract_parser.add_argument("--weeks", type=int, default=1)
    knowledge_extract_parser.add_argument("--model", default="cheap")
    knowledge_extract_parser.add_argument("--batch-size", type=int, default=12)
    knowledge_extract_parser.add_argument("--limit", type=int, default=0, help="Optional per-week post limit")
    knowledge_extract_parser.add_argument("--force", action="store_true", help="Rerun completed extraction batches")
    knowledge_extract_parser.set_defaults(handler=handle_knowledge_extract)

    idea_threads_parser = subparsers.add_parser(
        "idea-threads",
        help="Refresh temporal Idea Threads from persisted Knowledge Atoms",
    )
    idea_threads_parser.add_argument("--weeks", type=int, default=12)
    idea_threads_parser.add_argument("--limit", type=int, default=0, help="Optional atom limit for bounded refreshes")
    idea_threads_parser.set_defaults(handler=handle_idea_threads)

    frontier_parser = subparsers.add_parser(
        "frontier-analysis",
        help="Run top-model synthesis over Idea Threads and Knowledge Atoms",
    )
    frontier_parser.add_argument("--week", default=None, help="ISO week label, e.g. 2026-W28 (default: current UTC week)")
    frontier_parser.add_argument("--lookback-weeks", type=int, default=12)
    frontier_parser.add_argument("--model", default="strong", help="strong, mid, or explicit model id")
    frontier_parser.add_argument("--threads-limit", type=int, default=24)
    frontier_parser.add_argument("--atoms-limit", type=int, default=8)
    frontier_parser.add_argument("--force", action="store_true", help="Regenerate even when analysis already exists")
    frontier_parser.set_defaults(handler=handle_frontier_analysis)

    ai_report_parser = subparsers.add_parser(
        "ai-intelligence-report",
        help="Generate the standalone weekly AI Intelligence HTML report",
    )
    ai_report_parser.add_argument("--week", default=None, help="ISO week label, e.g. 2026-W28 (default: current UTC week)")
    ai_report_parser.add_argument("--threads-limit", type=int, default=8)
    ai_report_parser.add_argument("--atoms-limit", type=int, default=8)
    ai_report_parser.add_argument("--output-root", default=None)
    ai_report_parser.add_argument("--skip-refresh", action="store_true", help="Do not refresh Idea Threads before rendering")
    ai_report_parser.add_argument("--refresh-weeks", type=int, default=12, help="Idea Thread refresh lookback window")
    ai_report_parser.set_defaults(handler=handle_ai_intelligence_report)

    ai_visual_parser = subparsers.add_parser(
        "ai-visual-report",
        help="Generate an interactive Archify-backed AI Intelligence HTML artifact",
    )
    ai_visual_parser.add_argument("--week", default=None, help="ISO week label, e.g. 2026-W28 (default: current UTC week)")
    ai_visual_parser.add_argument("--threads-limit", type=int, default=12)
    ai_visual_parser.add_argument("--atoms-limit", type=int, default=8)
    ai_visual_parser.add_argument("--output-root", default=None)
    ai_visual_parser.add_argument("--archify-root", default=None, help="Path to the installed archify skill directory")
    ai_visual_parser.add_argument("--skip-refresh", action="store_true", help="Do not refresh Idea Threads before rendering")
    ai_visual_parser.add_argument("--refresh-weeks", type=int, default=12, help="Idea Thread refresh lookback window")
    ai_visual_parser.add_argument("--deliver", action="store_true", help="Send the HTML report to Telegram as a document")
    ai_visual_parser.add_argument("--chat-id", default=None, help="Telegram chat/channel id for --deliver")
    ai_visual_parser.add_argument("--token", default=None, help="Telegram bot token for --deliver")
    ai_visual_parser.set_defaults(handler=handle_ai_visual_report)

    obsidian_parser = subparsers.add_parser(
        "obsidian-export",
        help="Export the AI Intelligence knowledge layer into generated Obsidian Markdown notes",
    )
    obsidian_parser.add_argument("--week", default=None, help="ISO week label, e.g. 2026-W28 (default: current UTC week)")
    obsidian_parser.add_argument("--vault-path", default=None, help="Dedicated vault path (default: data/output/ai_intelligence_vault)")
    obsidian_parser.add_argument("--namespace", default=None, help="Optional scoped namespace inside the vault")
    obsidian_parser.add_argument("--report-root", default=None, help="Directory containing AI Intelligence HTML reports")
    obsidian_parser.add_argument("--threads-limit", type=int, default=100)
    obsidian_parser.add_argument("--atoms-limit", type=int, default=20)
    obsidian_parser.set_defaults(handler=handle_obsidian_export)

    mvp_weekly_parser = subparsers.add_parser(
        "mvp-weekly",
        help="Generate and optionally deliver the weekly MVP artifact through Demand-to-MVP Radar",
    )
    mvp_weekly_parser.add_argument("--days", type=int, default=7)
    mvp_weekly_parser.add_argument("--limit", type=int, default=80)
    mvp_weekly_parser.add_argument("--include-channel", action="append", default=[])
    mvp_weekly_parser.add_argument("--run-id", default=None)
    mvp_weekly_parser.add_argument("--no-deliver", action="store_true")
    mvp_weekly_parser.add_argument("--with-live-source-index", action="store_true")
    mvp_weekly_parser.add_argument("--live-intelligence-path", default=None)
    mvp_weekly_parser.add_argument("--live-index-days", type=int, default=None)
    mvp_weekly_parser.add_argument("--backfill-live-source-events", action="store_true")
    mvp_weekly_parser.set_defaults(handler=handle_mvp_weekly)

    channel_intel_report_parser = subparsers.add_parser(
        "channel-intelligence-report",
        help="Render an optional Markdown report from derived Channel Intelligence rows",
    )
    channel_intel_report_parser.add_argument("--week", required=True)
    channel_intel_report_parser.add_argument("--project", default=None)
    channel_intel_report_parser.add_argument("--topic", default=None)
    channel_intel_report_parser.add_argument("--limit", type=int, default=5)
    channel_intel_report_parser.set_defaults(handler=handle_channel_intelligence_report)

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

    operator_report_parser = subparsers.add_parser(
        "operator-report",
        help="Render a monthly operator report from local feedback, costs, and receipt health",
    )
    operator_report_parser.add_argument("--month", default=None, help="Month in YYYY-MM format (default: current UTC month)")
    operator_report_parser.set_defaults(handler=handle_operator_report)

    product_split_parser = subparsers.add_parser(
        "product-split-gate",
        help="Evaluate whether Telegram Channel Intelligence is ready for a product split",
    )
    product_split_parser.set_defaults(handler=handle_product_split_gate)

    ops_parser = subparsers.add_parser(
        "ops-validate",
        help="Validate production Telegram reaction and callback evidence from local state",
    )
    ops_parser.add_argument(
        "kind",
        nargs="?",
        choices=["all", "reaction-sync", "callbacks"],
        default="all",
    )
    ops_parser.add_argument("--days", type=int, default=14)
    ops_parser.set_defaults(handler=handle_ops_validate)

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

    usefulness_parser = subparsers.add_parser(
        "log-usefulness",
        help="Record operator usefulness feedback for a weekly Research Brief",
    )
    usefulness_parser.add_argument("--week", required=True, help="ISO week label for the brief, e.g. 2026-W22")
    usefulness_parser.add_argument("--useful-section", action="append", default=[])
    usefulness_parser.add_argument("--not-useful-section", action="append", default=[])
    usefulness_parser.add_argument("--decision", action="append", default=[])
    usefulness_parser.add_argument("--weak-evidence", action="append", default=[])
    usefulness_parser.add_argument("--trust-up", action="append", default=[])
    usefulness_parser.add_argument("--trust-down", action="append", default=[])
    usefulness_parser.add_argument("--notes", default=None)
    usefulness_parser.set_defaults(handler=handle_log_usefulness)

    artifact_feedback_parser = subparsers.add_parser(
        "log-artifact-feedback",
        help="Record operator feedback for a specific report artifact section or item",
    )
    artifact_feedback_parser.add_argument("--week", required=True, help="ISO week label, e.g. 2026-W22")
    artifact_feedback_parser.add_argument(
        "--feedback",
        required=True,
        choices=["useful", "weak", "noisy", "decision-impacting", "decision_impacting"],
    )
    artifact_feedback_parser.add_argument(
        "--artifact-type",
        default="research_brief",
        choices=["research_brief", "implementation_ideas", "mvp_weekly", "study_plan", "channel_intelligence", "other"],
    )
    artifact_feedback_parser.add_argument("--artifact-path", default=None)
    artifact_feedback_parser.add_argument("--digest-id", type=int, default=None)
    artifact_feedback_parser.add_argument("--section", default=None)
    artifact_feedback_parser.add_argument("--item-ref", default=None)
    artifact_feedback_parser.add_argument("--evidence-id", action="append", default=[])
    artifact_feedback_parser.add_argument("--notes", default=None)
    artifact_feedback_parser.set_defaults(handler=handle_log_artifact_feedback)

    ai_feedback_parser = subparsers.add_parser(
        "log-ai-report-feedback",
        help="Record read/try/missed/noise feedback for the AI Intelligence report",
    )
    ai_feedback_parser.add_argument("--week", required=True, help="ISO week label, e.g. 2026-W28")
    ai_feedback_parser.add_argument(
        "--feedback",
        required=True,
        choices=[
            "read",
            "useful",
            "tried",
            "applied-to-project",
            "applied_to_project",
            "too-shallow",
            "too_shallow",
            "missed-important-post",
            "missed_important_post",
            "wrong-priority",
            "wrong_priority",
            "not-interested",
            "not_interested",
            "noise",
        ],
    )
    ai_feedback_parser.add_argument(
        "--target-type",
        default="report",
        choices=[
            "report",
            "report-section",
            "report_section",
            "idea-thread",
            "idea_thread",
            "knowledge-atom",
            "knowledge_atom",
            "source-channel",
            "source_channel",
            "read-queue",
            "read_queue",
            "experiment",
            "action",
        ],
    )
    ai_feedback_parser.add_argument("--target-ref", default=None)
    ai_feedback_parser.add_argument("--report-path", default=None)
    ai_feedback_parser.add_argument("--source-url", default=None)
    ai_feedback_parser.add_argument("--notes", default=None)
    ai_feedback_parser.set_defaults(handler=handle_log_ai_report_feedback)

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
    is_parser.add_argument("--include-non-curated", action="store_true")
    is_parser.set_defaults(handler=handle_memory_inspect_snapshots)

    isupp_parser = memory_sub.add_parser("inspect-suppression")
    isupp_parser.add_argument("--title", required=True)
    isupp_parser.set_defaults(handler=handle_memory_inspect_suppression)

    af_parser = memory_sub.add_parser(
        "inspect-artifact-feedback",
        help="Inspect artifact-level operator feedback",
    )
    af_parser.add_argument("--week", default=None)
    af_parser.add_argument("--artifact-type", default=None)
    af_parser.add_argument("--artifact-path", default=None)
    af_parser.add_argument("--digest-id", type=int, default=None)
    af_parser.add_argument("--feedback", default=None)
    af_parser.add_argument("--limit", type=int, default=20)
    af_parser.set_defaults(handler=handle_memory_inspect_artifact_feedback)

    aif_parser = memory_sub.add_parser(
        "inspect-ai-report-feedback",
        help="Inspect AI Intelligence report feedback and missed-post eval examples",
    )
    aif_parser.add_argument("--week", default=None)
    aif_parser.add_argument("--feedback", default=None)
    aif_parser.add_argument("--target-type", default=None)
    aif_parser.add_argument("--target-ref", default=None)
    aif_parser.add_argument("--limit", type=int, default=20)
    aif_parser.add_argument("--eval-examples", action="store_true")
    aif_parser.set_defaults(handler=handle_memory_inspect_ai_report_feedback)

    atoms_parser = memory_sub.add_parser(
        "inspect-knowledge-atoms",
        help="Inspect extracted Knowledge Atom batches and atoms",
    )
    atoms_parser.add_argument("--week", default=None)
    atoms_parser.add_argument("--atom-type", default=None)
    atoms_parser.add_argument("--staleness", default=None)
    atoms_parser.add_argument("--batch-status", default=None)
    atoms_parser.add_argument("--limit", type=int, default=20)
    atoms_parser.set_defaults(handler=handle_memory_inspect_knowledge_atoms)

    threads_parser = memory_sub.add_parser(
        "inspect-idea-threads",
        help="Inspect Idea Threads and their source Knowledge Atom timeline",
    )
    threads_parser.add_argument("--slug", default=None)
    threads_parser.add_argument("--status", default=None)
    threads_parser.add_argument("--limit", type=int, default=10)
    threads_parser.add_argument("--atoms-limit", type=int, default=8)
    threads_parser.set_defaults(handler=handle_memory_inspect_idea_threads)

    editorial_parser = memory_sub.add_parser(
        "inspect-editorial-memory",
        help="Build and inspect weekly editorial memory",
    )
    editorial_parser.add_argument("--week", required=True)
    editorial_parser.add_argument("--output-root", default=None)
    editorial_parser.set_defaults(handler=handle_memory_inspect_editorial_memory)

    downrank_parser = memory_sub.add_parser(
        "explain-source-downrank",
        help="Explain source down-rank signals from observed local behavior",
    )
    downrank_parser.add_argument("--channel", default=None)
    downrank_parser.add_argument("--days", type=int, default=30)
    downrank_parser.add_argument("--limit", type=int, default=10)
    downrank_parser.set_defaults(handler=handle_memory_explain_source_downrank)

    diag_parser = memory_sub.add_parser(
        "diagnose-project-signals",
        help="Explain why digest topics did or did not link to active projects",
    )
    diag_parser.add_argument("--week", default=None)
    diag_parser.add_argument("--limit", type=int, default=10)
    diag_parser.add_argument("--json", action="store_true")
    diag_parser.set_defaults(handler=handle_memory_diagnose_project_signals)

    receipt_parser = memory_sub.add_parser(
        "inspect-receipts",
        help="Inspect Research Brief receipt audit metadata",
    )
    receipt_parser.add_argument("--receipt-id", default=None)
    receipt_parser.add_argument("--week", default=None)
    receipt_parser.add_argument("--digest-id", type=int, default=None)
    receipt_parser.add_argument("--artifact-path", default=None)
    receipt_parser.add_argument("--telegraph-url", default=None)
    receipt_parser.add_argument("--status", default=None)
    receipt_parser.add_argument("--limit", type=int, default=10)
    receipt_parser.set_defaults(handler=handle_memory_inspect_receipts)

    core_receipt_parser = memory_sub.add_parser(
        "inspect-core-receipt",
        help="Print the Core-compatible Research Brief receipt view",
    )
    core_receipt_parser.add_argument("--receipt-id", default=None)
    core_receipt_parser.add_argument("--week", default=None)
    core_receipt_parser.add_argument("--digest-id", type=int, default=None)
    core_receipt_parser.add_argument("--artifact-path", default=None)
    core_receipt_parser.add_argument("--telegraph-url", default=None)
    core_receipt_parser.add_argument("--status", default=None)
    core_receipt_parser.add_argument("--limit", type=int, default=1)
    core_receipt_parser.add_argument(
        "--verify-evidence",
        action="store_true",
        help="Include deterministic local lookup checks for Core evidence refs",
    )
    core_receipt_parser.set_defaults(handler=handle_memory_inspect_core_receipt)

    receipt_review_parser = memory_sub.add_parser(
        "review-receipt",
        help="Record operator review status for a Research Brief receipt",
    )
    receipt_review_parser.add_argument("--receipt-id", default=None)
    receipt_review_parser.add_argument("--week", default=None)
    receipt_review_parser.add_argument("--digest-id", type=int, default=None)
    receipt_review_parser.add_argument(
        "--status",
        required=True,
        choices=["verified", "waived", "needs_review", "failed"],
    )
    receipt_review_parser.add_argument("--notes", default=None)
    receipt_review_parser.add_argument("--checked-by", default="operator")
    receipt_review_parser.set_defaults(handler=handle_memory_review_receipt)

    intel_parser = memory_sub.add_parser(
        "inspect-channel-intelligence",
        help="Inspect Channel Intelligence claims, narratives, source observations, and links",
    )
    intel_parser.add_argument(
        "--kind",
        choices=["all", "claims", "narratives", "sources", "entity-links", "project-links"],
        default="all",
    )
    intel_parser.add_argument("--week", default=None)
    intel_parser.add_argument("--project", default=None)
    intel_parser.add_argument("--topic", default=None)
    intel_parser.add_argument("--channel", default=None)
    intel_parser.add_argument("--status", default=None)
    intel_parser.add_argument("--limit", type=int, default=10)
    intel_parser.set_defaults(handler=handle_memory_inspect_channel_intelligence)

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


def handle_bootstrap(args: argparse.Namespace) -> int:
    settings = load_settings()
    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")

        LOGGER.info("Starting step=bootstrap_ingest days=%d", args.days)
        bootstrap_summary = asyncio.run(run_bootstrap(settings, days=args.days))
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


def handle_export_opportunity_seeds(args: argparse.Namespace) -> int:
    settings = load_settings()
    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")
        output_path = Path(args.out) if args.out else None
        summary = export_opportunity_seeds(
            settings,
            days=max(1, args.days),
            limit=max(1, args.limit),
            output_path=output_path,
            include_channels=tuple(args.include_channel or ()),
        )
        LOGGER.info(
            "Finished step=export_opportunity_seeds week=%s seeds=%d scanned=%d knowledge_threads=%d output=%s",
            summary.week_label,
            summary.seed_count,
            summary.scanned_count,
            summary.knowledge_thread_count,
            summary.output_path,
        )
        sys.stdout.write(
            f"{summary.output_path}\n"
            f"seeds={summary.seed_count} scanned={summary.scanned_count} "
            f"knowledge_threads={summary.knowledge_thread_count} week={summary.week_label}\n"
        )
    except Exception:
        LOGGER.exception("Opportunity seed export failed")
        return 1
    return 0


def handle_live_source_index(args: argparse.Namespace) -> int:
    from output.live_source_intelligence import build_live_source_intelligence_snapshot
    from output.source_events import backfill_recent_source_events

    settings = load_settings()
    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")
        backfilled = 0
        if args.backfill_from_db:
            with sqlite3.connect(settings.db_path) as connection:
                connection.row_factory = sqlite3.Row
                backfilled = backfill_recent_source_events(
                    connection,
                    days=max(1, args.days),
                    event_root=args.event_root,
                )
        summary = build_live_source_intelligence_snapshot(
            days=max(1, args.days),
            event_root=args.event_root,
            output_path=args.out,
        )
        sys.stdout.write(
            f"{summary.output_path}\n"
            f"events={summary.event_count} repeated_claims={summary.repeated_claim_count} "
            f"week={summary.week_label} pathway_available={str(summary.pathway_available).lower()} "
            f"backfilled={backfilled}\n"
        )
    except Exception:
        LOGGER.exception("Live source index build failed")
        return 1
    return 0


def handle_mvp_weekly(args: argparse.Namespace) -> int:
    settings = load_settings()
    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")
        LOGGER.info("Starting step=mvp_weekly")
        summary = run_mvp_weekly_pipeline(
            settings,
            days=max(1, args.days),
            limit=max(1, args.limit),
            include_channels=tuple(args.include_channel or ()),
            run_id=args.run_id,
            deliver=not args.no_deliver,
            with_live_source_index=args.with_live_source_index,
            live_intelligence_path=args.live_intelligence_path,
            live_index_days=args.live_index_days,
            backfill_live_source_events=args.backfill_live_source_events,
        )
        LOGGER.info(
            "Finished step=mvp_weekly week=%s seeds=%d status=%s dossier_status=%s report=%s",
            summary.week_label,
            summary.seed_count,
            summary.radar_status,
            summary.dossier_status or "",
            summary.report_path or "",
        )
        sys.stdout.write(
            f"{summary.report_path or ''}\n"
            f"status={summary.radar_status} seeds={summary.seed_count} "
            f"knowledge_threads={summary.knowledge_thread_count} "
            f"dossier_status={summary.dossier_status or ''} "
            f"title={summary.selected_title or ''}\n"
            f"live_intelligence={summary.live_intelligence_path or ''}\n"
            f"telegraph={summary.telegraph_url or ''}\n"
        )
    except Exception:
        LOGGER.exception("MVP weekly pipeline failed")
        return 1
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
            receipt_health_rows = connection.execute(
                """
                SELECT week_label, generated_at, post_counts_json, health_flags_json
                FROM research_brief_receipts
                ORDER BY week_label DESC, generated_at DESC, id DESC
                LIMIT 16
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

    latest_receipt_by_week: dict[str, sqlite3.Row] = {}
    for row in receipt_health_rows:
        week = str(row["week_label"] or "")
        if week and week not in latest_receipt_by_week:
            latest_receipt_by_week[week] = row
    if latest_receipt_by_week:
        lines.append("digest_health_trend (latest receipt per week):")
        empty_alerts = 0
        low_signal_alerts = 0
        for week, row in list(latest_receipt_by_week.items())[:8]:
            try:
                flags = json.loads(row["health_flags_json"] or "[]")
            except json.JSONDecodeError:
                flags = []
            try:
                post_counts = json.loads(row["post_counts_json"] or "{}")
            except json.JSONDecodeError:
                post_counts = {}
            if "empty_week_alert" in flags:
                empty_alerts += 1
            if "low_signal_alert" in flags:
                low_signal_alerts += 1
            lines.append(
                f"  {week}: flags={','.join(flags) if flags else 'none'} "
                f"total_posts={int(post_counts.get('total_posts') or 0)} "
                f"strong={int(post_counts.get('strong_count') or 0)} "
                f"watch={int(post_counts.get('watch_count') or 0)}"
            )
        lines.append(f"digest_health_alerts_last_{min(8, len(latest_receipt_by_week))}: empty={empty_alerts} low_signal={low_signal_alerts}")
    else:
        lines.append("digest_health_trend: no Research Brief receipts recorded")

    sys.stdout.write("\n".join(lines) + "\n")
    return 0


def handle_cost_stats(_: argparse.Namespace) -> int:
    from output.cost_guardrails import (
        evaluate_llm_cost_guardrails,
        format_cost_guardrail_lines,
    )

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
            guardrail_report = evaluate_llm_cost_guardrails(connection)
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
    lines.append("guardrails:")
    lines.extend(
        "  " + line[2:] if line.startswith("- ") else "  " + line
        for line in format_cost_guardrail_lines(guardrail_report)
    )

    sys.stdout.write("\n".join(lines) + "\n")
    return 0


def handle_operator_report(args: argparse.Namespace) -> int:
    from output.operator_report import build_monthly_operator_report

    settings = load_settings()

    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")

        with sqlite3.connect(settings.db_path) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON;")
            report = build_monthly_operator_report(connection, month=args.month)
    except Exception as exc:
        sys.stdout.write(f"Error rendering operator report: {exc}\n")
        return 1

    sys.stdout.write(report)
    return 0


def handle_product_split_gate(_: argparse.Namespace) -> int:
    from output.product_split import evaluate_product_split_gate, format_product_split_gate

    settings = load_settings()

    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")

        with sqlite3.connect(settings.db_path) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON;")
            evaluation = evaluate_product_split_gate(connection)
    except Exception as exc:
        sys.stdout.write(f"Error evaluating product split gate: {exc}\n")
        return 1

    sys.stdout.write(format_product_split_gate(evaluation))
    return 0


def handle_ops_validate(args: argparse.Namespace) -> int:
    from output.ops_validation import format_ops_validation, validate_ops

    settings = load_settings()

    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")

        with sqlite3.connect(settings.db_path) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON;")
            results = validate_ops(connection, kind=args.kind, days=args.days)
    except Exception as exc:
        sys.stdout.write(f"Error validating ops paths: {exc}\n")
        return 1

    sys.stdout.write(format_ops_validation(results))
    return 0


def _config_status_lines() -> list[str]:
    config_paths = (
        PROJECT_ROOT / "src" / "config" / "profile.yaml",
        PROJECT_ROOT / "src" / "config" / "projects.yaml",
        PROJECT_ROOT / "src" / "config" / "scoring.yaml",
    )
    lines = [f"{path.name}: {'present' if path.exists() else 'missing'}" for path in config_paths]
    projects_path = PROJECT_ROOT / "src" / "config" / "projects.yaml"
    if projects_path.exists():
        modified_at = datetime.fromtimestamp(projects_path.stat().st_mtime, tz=timezone.utc)
        age_days = max(0, (datetime.now(timezone.utc) - modified_at).days)
        lines.append(f"projects_yaml_review: last_modified={modified_at.date().isoformat()} age_days={age_days}")
        if age_days > 31:
            lines.append("WARNING: projects.yaml has not changed in over 31 days; review active project config")
    else:
        lines.append("projects_yaml_review: missing")
    return lines


def handle_health_check(_: argparse.Namespace) -> int:
    from output.context_memory import _project_is_curated

    db_path_raw = os.environ.get("AGENT_DB_PATH", "").strip() or os.environ.get("DB_PATH", "").strip()
    lines: list[str] = []
    exit_code = 0

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
                project_rows = connection.execute(
                    """
                    SELECT name, github_repo
                    FROM projects
                    WHERE active = 1
                    """
                ).fetchall()
                active_projects_count = len(project_rows)
                curated_active_projects_count = sum(
                    1
                    for row in project_rows
                    if _project_is_curated(str(row["name"] or ""), str(row["github_repo"] or ""))
                )
                non_curated_active_projects_count = active_projects_count - curated_active_projects_count
                project_relevance_count = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM posts WHERE COALESCE(project_relevance_score, 0) > 0"
                    ).fetchone()[0]
                )
                project_matches_present_count = int(
                    connection.execute(
                        """
                        SELECT COUNT(*)
                        FROM posts
                        WHERE project_matches IS NOT NULL
                          AND project_matches NOT IN ('[]', 'null', '')
                        """
                    ).fetchone()[0]
                )
                post_project_links_count = int(
                    connection.execute("SELECT COUNT(*) FROM post_project_links").fetchone()[0]
                )
                project_scoped_evidence_count = int(
                    connection.execute(
                        """
                        SELECT COUNT(*)
                        FROM signal_evidence_items
                        WHERE project_names_json NOT IN ('[]', 'null', '')
                        """
                    ).fetchone()[0]
                )
                zero_signal_snapshot_rows = connection.execute(
                    """
                    SELECT project_name, github_repo
                    FROM project_context_snapshots
                    WHERE COALESCE(linked_signal_count, 0) = 0
                    """
                ).fetchall()
                zero_signal_snapshots_count = sum(
                    1
                    for row in zero_signal_snapshot_rows
                    if _project_is_curated(str(row["project_name"] or ""), str(row["github_repo"] or ""))
                )
                weekly_delivery_health = build_weekly_delivery_health(
                    connection=connection,
                    project_root=PROJECT_ROOT,
                )
        except Exception as exc:
            lines.append(f"db_error: {exc}")
        else:
            lines.append(f"posts: {posts_count}")
            lines.append(f"scored_posts: {scored_posts_count}")
            lines.append(f"active_projects: {active_projects_count}")
            lines.append(f"curated_active_projects: {curated_active_projects_count}")
            lines.append(f"non_curated_active_projects: {non_curated_active_projects_count}")
            lines.append(f"project_relevance_posts: {project_relevance_count}")
            lines.append(f"project_matches_present: {project_matches_present_count}")
            lines.append(f"post_project_links: {post_project_links_count}")
            lines.append(f"project_scoped_evidence: {project_scoped_evidence_count}")
            lines.append(f"zero_signal_snapshots: {zero_signal_snapshots_count}")
            lines.append(f"llm_usage: {llm_usage_count}")
            lines.append(f"last_ingestion: {last_ingestion}")
            lines.append(f"last_scored: {last_scored}")
            lines.append(f"last_digest: {last_digest}")
            lines.extend(format_weekly_delivery_health(weekly_delivery_health, relative_to=PROJECT_ROOT))
            if weekly_delivery_health.failure_reasons:
                exit_code = 1
            if unscored_count > 0:
                lines.append(f"WARNING: {unscored_count} posts pending scoring (stuck queue?)")
            if project_relevance_count > 0 and project_matches_present_count == 0:
                lines.append("WARNING: project relevance exists but project_matches are empty; rerun scoring")
            if project_matches_present_count > 0 and post_project_links_count == 0:
                lines.append(
                    "WARNING: project_matches exist but no high-confidence project links; run diagnose-project-signals"
                )
            if non_curated_active_projects_count > 0:
                lines.append("WARNING: non-curated active projects exist; scoped outputs use projects.yaml")
    else:
        lines.append("db_status: missing")

    lines.extend(_config_status_lines())
    sys.stdout.write("\n".join(lines) + "\n")
    return exit_code


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


def handle_knowledge_extract(args: argparse.Namespace) -> int:
    from output.knowledge_extraction import format_knowledge_extraction_summary, run_knowledge_extraction

    settings = load_settings()

    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")

        LOGGER.info(
            "Starting step=knowledge_extract weeks=%d model=%s batch_size=%d",
            args.weeks,
            args.model,
            args.batch_size,
        )
        summary = run_knowledge_extraction(
            settings,
            weeks=args.weeks,
            model=args.model,
            batch_size=args.batch_size,
            limit=args.limit if args.limit and args.limit > 0 else None,
            force=bool(args.force),
        )
        LOGGER.info(
            "Finished step=knowledge_extract posts=%d batches=%d atoms=%d errors=%d",
            summary.posts_seen,
            summary.batches_total,
            summary.atoms_recorded,
            len(summary.errors),
        )
    except Exception as exc:
        LOGGER.exception("Knowledge extraction failed")
        sys.stdout.write(f"Knowledge extraction failed: {exc}\n")
        return 1

    sys.stdout.write(format_knowledge_extraction_summary(summary))
    return 0 if not summary.errors else 1


def handle_idea_threads(args: argparse.Namespace) -> int:
    from output.idea_threads import format_idea_thread_summary, refresh_idea_threads

    settings = load_settings()

    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")

        LOGGER.info("Starting step=idea_threads weeks=%d limit=%d", args.weeks, args.limit)
        summary = refresh_idea_threads(
            settings,
            weeks=max(1, args.weeks),
            limit=args.limit if args.limit and args.limit > 0 else None,
        )
        LOGGER.info(
            "Finished step=idea_threads atoms=%d threads=%d links=%d",
            summary.atoms_seen,
            summary.threads_refreshed,
            summary.links_refreshed,
        )
    except Exception as exc:
        LOGGER.exception("Idea Thread refresh failed")
        sys.stdout.write(f"Idea Thread refresh failed: {exc}\n")
        return 1

    sys.stdout.write(format_idea_thread_summary(summary))
    return 0


def handle_frontier_analysis(args: argparse.Namespace) -> int:
    from output.frontier_analysis import format_frontier_analysis_summary, run_frontier_analysis

    settings = load_settings()

    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")

        LOGGER.info(
            "Starting step=frontier_analysis week=%s lookback_weeks=%d model=%s",
            args.week or "current",
            args.lookback_weeks,
            args.model,
        )
        summary = run_frontier_analysis(
            settings,
            week_label=args.week,
            lookback_weeks=max(1, args.lookback_weeks),
            model=args.model,
            threads_limit=max(1, args.threads_limit),
            atoms_limit=max(1, args.atoms_limit),
            force=bool(args.force),
        )
        LOGGER.info(
            "Finished step=frontier_analysis week=%s threads=%d atoms=%d actions=%d skipped=%s",
            summary.week_label,
            summary.threads_analyzed,
            summary.atoms_analyzed,
            summary.action_count,
            summary.skipped_existing,
        )
    except Exception as exc:
        LOGGER.exception("Frontier analysis failed")
        sys.stdout.write(f"Frontier analysis failed: {exc}\n")
        return 1

    sys.stdout.write(format_frontier_analysis_summary(summary))
    return 0


def handle_ai_intelligence_report(args: argparse.Namespace) -> int:
    from output.ai_intelligence_report import (
        AiIntelligenceReportQualityError,
        generate_ai_intelligence_report,
    )
    from output.idea_threads import refresh_idea_threads

    settings = load_settings()

    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")

        if not args.skip_refresh:
            LOGGER.info("Starting step=idea_threads refresh_weeks=%d", args.refresh_weeks)
            refresh_idea_threads(settings, weeks=max(1, args.refresh_weeks))
            LOGGER.info("Finished step=idea_threads")

        LOGGER.info(
            "Starting step=ai_intelligence_report week=%s threads_limit=%d atoms_limit=%d",
            args.week or "current",
            args.threads_limit,
            args.atoms_limit,
        )
        summary = generate_ai_intelligence_report(
            settings,
            week_label=args.week,
            threads_limit=max(1, args.threads_limit),
            atoms_limit=max(1, args.atoms_limit),
            output_root=args.output_root,
        )
        LOGGER.info(
            "Finished step=ai_intelligence_report week=%s threads=%d atoms=%d output=%s",
            summary.week_label,
            summary.thread_count,
            summary.source_atom_count,
            summary.html_path,
        )
    except AiIntelligenceReportQualityError as exc:
        LOGGER.exception("AI Intelligence report failed quality gates")
        lines = ["AI Intelligence report failed quality gates:"]
        lines.extend(f"- {finding.message}" for finding in exc.findings)
        sys.stdout.write("\n".join(lines) + "\n")
        return 1
    except Exception as exc:
        LOGGER.exception("AI Intelligence report generation failed")
        sys.stdout.write(f"AI Intelligence report generation failed: {exc}\n")
        return 1

    sys.stdout.write(
        f"{summary.html_path}\n"
        f"json={summary.json_path}\n"
        f"week={summary.week_label} threads={summary.thread_count} "
        f"source_atoms={summary.source_atom_count} source_channels={summary.source_channel_count} "
        f"actions={summary.action_count} quality_findings={summary.quality_finding_count}\n"
        f"notification={summary.notification_text}\n"
    )
    return 0


def handle_ai_visual_report(args: argparse.Namespace) -> int:
    from output.ai_visual_report import (
        AiVisualReportQualityError,
        deliver_ai_visual_report,
        generate_ai_visual_report,
    )
    from output.idea_threads import refresh_idea_threads

    settings = load_settings()

    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")

        if not args.skip_refresh:
            LOGGER.info("Starting step=idea_threads refresh_weeks=%d", args.refresh_weeks)
            refresh_idea_threads(settings, weeks=max(1, args.refresh_weeks))
            LOGGER.info("Finished step=idea_threads")

        LOGGER.info(
            "Starting step=ai_visual_report week=%s threads_limit=%d atoms_limit=%d archify_root=%s",
            args.week or "current",
            args.threads_limit,
            args.atoms_limit,
            args.archify_root or "auto",
        )
        summary = generate_ai_visual_report(
            settings,
            week_label=args.week,
            threads_limit=max(1, args.threads_limit),
            atoms_limit=max(1, args.atoms_limit),
            output_root=args.output_root,
            archify_root=args.archify_root,
        )
        if args.deliver:
            summary = deliver_ai_visual_report(
                summary,
                chat_id=args.chat_id,
                token=args.token,
            )
        LOGGER.info(
            "Finished step=ai_visual_report week=%s threads=%d atoms=%d output=%s archify=%s delivered=%s",
            summary.week_label,
            summary.thread_count,
            summary.source_atom_count,
            summary.html_path,
            summary.archify_status,
            summary.delivered_message_id,
        )
    except AiVisualReportQualityError as exc:
        LOGGER.exception("AI Visual report failed quality gates")
        lines = ["AI Visual report failed quality gates:"]
        lines.extend(f"- {finding.message}" for finding in exc.findings)
        sys.stdout.write("\n".join(lines) + "\n")
        return 1
    except Exception as exc:
        LOGGER.exception("AI Visual report generation failed")
        sys.stdout.write(f"AI Visual report generation failed: {exc}\n")
        return 1

    sys.stdout.write(
        f"{summary.html_path}\n"
        f"json={summary.json_path}\n"
        f"diagram={summary.diagram_html_path}\n"
        f"diagram_ir={summary.diagram_ir_path}\n"
        f"week={summary.week_label} threads={summary.thread_count} "
        f"source_atoms={summary.source_atom_count} source_channels={summary.source_channel_count} "
        f"project_links={summary.project_link_count} actions={summary.action_count} "
        f"archify={summary.archify_status} quality_findings={summary.quality_finding_count}\n"
        f"delivered_message_id={summary.delivered_message_id or ''}\n"
        f"notification={summary.notification_text}\n"
    )
    return 0


def handle_obsidian_export(args: argparse.Namespace) -> int:
    from output.obsidian_export import ObsidianExportError, export_obsidian_vault

    settings = load_settings()

    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")

        LOGGER.info(
            "Starting step=obsidian_export week=%s vault=%s namespace=%s",
            args.week or "current",
            args.vault_path or "default",
            args.namespace or "",
        )
        summary = export_obsidian_vault(
            settings,
            week_label=args.week,
            vault_path=args.vault_path,
            namespace=args.namespace,
            report_root=args.report_root,
            threads_limit=max(1, args.threads_limit),
            atoms_limit=max(1, args.atoms_limit),
        )
        LOGGER.info(
            "Finished step=obsidian_export week=%s files=%d vault=%s",
            summary.week_label,
            summary.files_written,
            summary.vault_root,
        )
    except ObsidianExportError as exc:
        LOGGER.exception("Obsidian export failed validation")
        sys.stdout.write(f"Obsidian export failed: {exc}\n")
        return 1
    except Exception as exc:
        LOGGER.exception("Obsidian export failed")
        sys.stdout.write(f"Obsidian export failed: {exc}\n")
        return 1

    sys.stdout.write(
        f"{summary.vault_root}\n"
        f"week={summary.week_label} files={summary.files_written} "
        f"threads={summary.thread_count} source_atoms={summary.source_atom_count} "
        f"terms={summary.term_note_count} channels={summary.channel_note_count} "
        f"read_queue={summary.read_queue_note_count} experiments={summary.experiment_note_count}\n"
    )
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


def handle_log_usefulness(args: argparse.Namespace) -> int:
    from db.usefulness import record_weekly_usefulness_log

    settings = load_settings()

    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")

        with sqlite3.connect(settings.db_path) as connection:
            connection.execute("PRAGMA foreign_keys = ON;")
            connection.execute("PRAGMA journal_mode = WAL;")
            log = record_weekly_usefulness_log(
                connection,
                week_label=args.week,
                useful_sections=args.useful_section,
                not_useful_sections=args.not_useful_section,
                decisions_influenced=args.decision,
                weak_evidence_notes=args.weak_evidence,
                channels_gaining_trust=args.trust_up,
                channels_losing_trust=args.trust_down,
                notes=args.notes,
            )
    except Exception as exc:
        LOGGER.exception("Usefulness log recording failed")
        sys.stdout.write(f"Failed to record usefulness log: {exc}\n")
        return 1

    lines = [
        f"Recorded weekly usefulness log id={log['id']} week={log['week_label']}",
        f"recorded_at={log['recorded_at']}",
        (
            "counts: "
            f"useful_sections={len(log['useful_sections'])} "
            f"not_useful_sections={len(log['not_useful_sections'])} "
            f"decisions={len(log['decisions_influenced'])} "
            f"weak_evidence={len(log['weak_evidence_notes'])} "
            f"trust_up={len(log['channels_gaining_trust'])} "
            f"trust_down={len(log['channels_losing_trust'])}"
        ),
    ]
    if log.get("notes"):
        lines.append(f"notes={log['notes']}")
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


def handle_log_artifact_feedback(args: argparse.Namespace) -> int:
    from db.artifact_feedback import record_artifact_feedback

    settings = load_settings()

    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")

        with sqlite3.connect(settings.db_path) as connection:
            connection.execute("PRAGMA foreign_keys = ON;")
            connection.execute("PRAGMA journal_mode = WAL;")
            feedback = record_artifact_feedback(
                connection,
                week_label=args.week,
                artifact_type=args.artifact_type,
                artifact_path=args.artifact_path,
                digest_id=args.digest_id,
                section=args.section,
                item_ref=args.item_ref,
                feedback=args.feedback,
                source_evidence_item_ids=args.evidence_id,
                notes=args.notes,
            )
    except Exception as exc:
        LOGGER.exception("Artifact feedback recording failed")
        sys.stdout.write(f"Failed to record artifact feedback: {exc}\n")
        return 1

    lines = [
        f"Recorded artifact feedback id={feedback['id']} week={feedback['week_label']}",
        f"artifact_type={feedback['artifact_type']} feedback={feedback['feedback']}",
        f"target=section:{feedback.get('section') or 'n/a'} item_ref:{feedback.get('item_ref') or 'n/a'}",
        f"evidence_ids={_format_receipt_list(feedback.get('source_evidence_item_ids'))}",
        f"recorded_at={feedback['recorded_at']}",
    ]
    if feedback.get("artifact_path"):
        lines.append(f"artifact_path={feedback['artifact_path']}")
    if feedback.get("digest_id") is not None:
        lines.append(f"digest_id={feedback['digest_id']}")
    if feedback.get("notes"):
        lines.append(f"notes={feedback['notes']}")
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


def handle_log_ai_report_feedback(args: argparse.Namespace) -> int:
    from db.ai_report_feedback import record_ai_report_feedback

    settings = load_settings()

    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")

        with sqlite3.connect(settings.db_path) as connection:
            connection.execute("PRAGMA foreign_keys = ON;")
            connection.execute("PRAGMA journal_mode = WAL;")
            feedback = record_ai_report_feedback(
                connection,
                week_label=args.week,
                feedback_type=args.feedback,
                target_type=args.target_type,
                target_ref=args.target_ref,
                report_path=args.report_path,
                source_url=args.source_url,
                notes=args.notes,
            )
    except Exception as exc:
        LOGGER.exception("AI report feedback recording failed")
        sys.stdout.write(f"Failed to record AI report feedback: {exc}\n")
        return 1

    lines = [
        f"Recorded AI report feedback id={feedback['id']} week={feedback['week_label']}",
        f"feedback={feedback['feedback_type']} target={feedback['target_type']}:{feedback.get('target_ref') or 'report'}",
        f"recorded_at={feedback['created_at']}",
    ]
    if feedback.get("source_url"):
        lines.append(f"source_url={feedback['source_url']}")
    if feedback.get("report_path"):
        lines.append(f"report_path={feedback['report_path']}")
    if feedback.get("notes"):
        lines.append(f"notes={feedback['notes']}")
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


def _format_artifact_feedback(feedback: dict) -> str:
    lines = [
        f"ArtifactFeedback {feedback.get('id')}",
        f"  week={feedback.get('week_label') or 'n/a'} type={feedback.get('artifact_type') or 'n/a'} feedback={feedback.get('feedback') or 'n/a'}",
        f"  artifact_path={feedback.get('artifact_path') or 'n/a'} digest_id={feedback.get('digest_id') or 'n/a'}",
        f"  target: section={feedback.get('section') or 'n/a'} item_ref={feedback.get('item_ref') or 'n/a'}",
        f"  source_evidence_item_ids={_format_receipt_list(feedback.get('source_evidence_item_ids'))}",
        f"  recorded_at={feedback.get('recorded_at') or 'n/a'} recorded_by={feedback.get('recorded_by') or 'n/a'}",
        f"  notes={feedback.get('notes') or 'n/a'}",
    ]
    return "\n".join(lines)


def handle_memory_inspect_artifact_feedback(args: argparse.Namespace) -> int:
    from db.artifact_feedback import fetch_artifact_feedback

    settings = load_settings()

    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")

        with sqlite3.connect(settings.db_path) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON;")
            rows = fetch_artifact_feedback(
                connection,
                week_label=args.week,
                artifact_type=args.artifact_type,
                artifact_path=args.artifact_path,
                digest_id=args.digest_id,
                feedback=args.feedback,
                limit=args.limit,
            )
    except Exception as exc:
        sys.stdout.write(f"Error inspecting artifact feedback: {exc}\n")
        return 1

    if not rows:
        sys.stdout.write("No artifact feedback found for the given scope.\n")
        return 0

    sys.stdout.write(("\n\n".join(_format_artifact_feedback(row) for row in rows)).rstrip() + "\n")
    return 0


def _format_ai_report_feedback(row: dict) -> str:
    lines = [
        f"AIReportFeedback {row.get('id')}",
        (
            f"  week={row.get('week_label') or 'n/a'} feedback={row.get('feedback_type') or 'n/a'} "
            f"target={row.get('target_type') or 'n/a'}:{row.get('target_ref') or 'report'}"
        ),
        f"  report_path={row.get('report_path') or 'n/a'}",
        f"  source_url={row.get('source_url') or 'n/a'}",
        f"  recorded_at={row.get('created_at') or 'n/a'} recorded_by={row.get('recorded_by') or 'n/a'}",
        f"  notes={row.get('notes') or 'n/a'}",
    ]
    return "\n".join(lines)


def handle_memory_inspect_ai_report_feedback(args: argparse.Namespace) -> int:
    from db.ai_report_feedback import (
        fetch_ai_report_feedback,
        fetch_missed_post_eval_examples,
        format_ai_report_feedback_summary,
        summarize_ai_report_feedback,
    )

    settings = load_settings()

    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")

        with sqlite3.connect(settings.db_path) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON;")
            rows = fetch_ai_report_feedback(
                connection,
                week_label=args.week,
                feedback_type=args.feedback,
                target_type=args.target_type,
                target_ref=args.target_ref,
                limit=args.limit,
            )
            summary = summarize_ai_report_feedback(
                connection,
                week_label=args.week,
                limit=max(args.limit, 100),
            )
            eval_examples = (
                fetch_missed_post_eval_examples(connection, week_label=args.week, limit=args.limit)
                if args.eval_examples
                else []
            )
    except Exception as exc:
        sys.stdout.write(f"Error inspecting AI report feedback: {exc}\n")
        return 1

    lines = [
        "AI Report Feedback inspection",
        "source_of_truth: ai_report_feedback_events",
        "retrieval_path: week, feedback_type, target_type, target_ref, missed-post eval examples",
        (
            f"scope: week={args.week or 'any'} feedback={args.feedback or 'any'} "
            f"target_type={args.target_type or 'any'} target_ref={args.target_ref or 'any'}"
        ),
        f"summary: {format_ai_report_feedback_summary(summary)}",
        f"events ({len(rows)}):",
    ]
    if rows:
        lines.extend(_format_ai_report_feedback(row) for row in rows)
    else:
        lines.append("  none")
    if args.eval_examples:
        lines.append(f"missed_post_eval_examples ({len(eval_examples)}):")
        if eval_examples:
            for example in eval_examples:
                lines.append(
                    f"  - week={example.get('week_label')} source_url={example.get('source_url') or 'n/a'} "
                    f"target_ref={example.get('target_ref') or 'n/a'} notes={example.get('notes') or 'n/a'}"
                )
        else:
            lines.append("  none")

    sys.stdout.write("\n".join(lines).rstrip() + "\n")
    return 0


def _format_knowledge_atom(atom: dict) -> str:
    source_urls = atom.get("source_urls") or []
    entities = atom.get("entities") or []
    lines = [
        f"KnowledgeAtom {atom.get('id')}",
        (
            f"  week={atom.get('week_label') or 'n/a'} type={atom.get('atom_type') or 'n/a'} "
            f"staleness={atom.get('staleness_status') or 'n/a'} confidence={atom.get('confidence') or 0:.2f} "
            f"novelty={atom.get('novelty_score') or 0:.2f} utility={atom.get('practical_utility_score') or 0:.2f}"
        ),
        f"  claim={atom.get('claim') or 'n/a'}",
        f"  evidence={atom.get('evidence_quote') or 'n/a'}",
        f"  sources={', '.join(source_urls[:3]) if source_urls else 'n/a'}",
        f"  entities={', '.join(entities[:8]) if entities else 'n/a'}",
        f"  atom_key={atom.get('atom_key') or 'n/a'} batch_id={atom.get('extraction_batch_id') or 'n/a'}",
    ]
    if atom.get("why_it_matters"):
        lines.append(f"  why_it_matters={atom['why_it_matters']}")
    return "\n".join(lines)


def handle_memory_inspect_knowledge_atoms(args: argparse.Namespace) -> int:
    from db.knowledge_atoms import fetch_knowledge_atoms, fetch_knowledge_extraction_batches

    settings = load_settings()

    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")

        with sqlite3.connect(settings.db_path) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON;")
            batches = fetch_knowledge_extraction_batches(
                connection,
                week_label=args.week,
                status=args.batch_status,
                limit=args.limit,
            )
            atoms = fetch_knowledge_atoms(
                connection,
                week_label=args.week,
                atom_type=args.atom_type,
                staleness_status=args.staleness,
                limit=args.limit,
            )
    except Exception as exc:
        sys.stdout.write(f"Error inspecting Knowledge Atoms: {exc}\n")
        return 1

    lines = [
        "Knowledge Atom inspection",
        "source_of_truth: knowledge_extraction_batches, knowledge_atoms, posts/raw_posts source citations",
        "refresh_rule: derived rows are created by knowledge-extract; raw Telegram posts remain authoritative",
        "retrieval_path: week, atom_type, staleness_status, batch status, source post IDs and URLs",
        (
            "scope: "
            f"week={args.week or 'any'} atom_type={args.atom_type or 'any'} "
            f"staleness={args.staleness or 'any'} batch_status={args.batch_status or 'any'}"
        ),
        f"batches ({len(batches)}):",
    ]
    if batches:
        for batch in batches:
            lines.append(
                f"  - id={batch['id']} week={batch['week_label']} channel={batch.get('channel_username') or 'all'} "
                f"status={batch['status']} posts={batch['post_count']} model={batch['model']} "
                f"started={batch['started_at']} completed={batch.get('completed_at') or 'n/a'}"
            )
            if batch.get("error"):
                lines.append(f"    error={batch['error']}")
    else:
        lines.append("  none")
    lines.append(f"atoms ({len(atoms)}):")
    if atoms:
        lines.extend(_format_knowledge_atom(atom) for atom in atoms)
    else:
        lines.append("  none")

    sys.stdout.write("\n".join(lines).rstrip() + "\n")
    return 0


def _format_idea_thread(thread: dict, atoms: list[dict]) -> str:
    source_channels = thread.get("source_channels") or []
    key_entities = thread.get("key_entities") or []
    current_claims = thread.get("current_claims") or []
    superseded_claims = thread.get("superseded_claims") or []
    contradictions = thread.get("contradictions") or []
    lines = [
        f"IdeaThread {thread.get('id')} {thread.get('slug')}",
        (
            f"  status={thread.get('status') or 'n/a'} atom_count={thread.get('atom_count') or 0} "
            f"channels={thread.get('source_channel_count') or 0} "
            f"momentum_7d={thread.get('momentum_7d') or 0:.2f} "
            f"momentum_30d={thread.get('momentum_30d') or 0:.2f} "
            f"momentum_90d={thread.get('momentum_90d') or 0:.2f}"
        ),
        f"  title={thread.get('title') or 'n/a'}",
        f"  first_seen={thread.get('first_seen_at') or 'n/a'} last_seen={thread.get('last_seen_at') or 'n/a'}",
        f"  source_channels={', '.join(source_channels[:8]) if source_channels else 'n/a'}",
        f"  key_entities={', '.join(key_entities[:8]) if key_entities else 'n/a'}",
        f"  current_claims={'; '.join(current_claims[:3]) if current_claims else 'n/a'}",
    ]
    if superseded_claims:
        lines.append(f"  superseded_claims={'; '.join(superseded_claims[:3])}")
    if contradictions:
        lines.append(f"  contradictions={'; '.join(contradictions[:3])}")
    lines.append(f"  timeline_atoms ({len(atoms)}):")
    if atoms:
        for atom in atoms:
            source_urls = atom.get("source_urls") or []
            lines.append(
                f"    - atom={atom.get('id')} relation={atom.get('relation') or 'n/a'} "
                f"type={atom.get('atom_type') or 'n/a'} staleness={atom.get('staleness_status') or 'n/a'} "
                f"last_seen={atom.get('last_seen_at') or 'n/a'}"
            )
            lines.append(f"      claim={atom.get('claim') or 'n/a'}")
            lines.append(f"      sources={', '.join(source_urls[:3]) if source_urls else 'n/a'}")
    else:
        lines.append("    none")
    return "\n".join(lines)


def handle_memory_inspect_idea_threads(args: argparse.Namespace) -> int:
    from db.idea_threads import fetch_idea_thread_atoms, fetch_idea_threads

    settings = load_settings()

    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")

        with sqlite3.connect(settings.db_path) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON;")
            threads = fetch_idea_threads(
                connection,
                slug=args.slug,
                status=args.status,
                limit=args.limit,
            )
            thread_atoms = {
                thread["id"]: fetch_idea_thread_atoms(
                    connection,
                    thread_id=thread["id"],
                    limit=args.atoms_limit,
                )
                for thread in threads
            }
    except Exception as exc:
        sys.stdout.write(f"Error inspecting Idea Threads: {exc}\n")
        return 1

    lines = [
        "Idea Thread inspection",
        "source_of_truth: idea_threads, idea_thread_atoms, knowledge_atoms",
        "refresh_rule: derived rows are refreshed by idea-threads; stale status preserves source evidence",
        "retrieval_path: slug, status, momentum, source Knowledge Atom timeline",
        f"scope: slug={args.slug or 'any'} status={args.status or 'any'}",
        f"threads ({len(threads)}):",
    ]
    if threads:
        lines.extend(_format_idea_thread(thread, thread_atoms.get(thread["id"], [])) for thread in threads)
    else:
        lines.append("  none")

    sys.stdout.write("\n".join(lines).rstrip() + "\n")
    return 0


def handle_memory_inspect_editorial_memory(args: argparse.Namespace) -> int:
    from output.editorial_memory import build_weekly_editorial_memory

    settings = load_settings()

    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")

        with sqlite3.connect(settings.db_path) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON;")
            memory = build_weekly_editorial_memory(
                connection,
                week_label=args.week,
                output_root=args.output_root,
                write_sidecar=True,
            )
    except Exception as exc:
        sys.stdout.write(f"Error inspecting editorial memory: {exc}\n")
        return 1

    if memory.sidecar_path is not None:
        sys.stdout.write(f"sidecar={memory.sidecar_path}\n")
    sys.stdout.write(memory.markdown)
    return 0


def handle_memory_explain_source_downrank(args: argparse.Namespace) -> int:
    from output.source_trust import explain_source_downrank, format_source_downrank_explanations

    settings = load_settings()

    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")

        with sqlite3.connect(settings.db_path) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON;")
            explanations = explain_source_downrank(
                connection,
                channel=args.channel,
                days=args.days,
                limit=args.limit,
            )
    except Exception as exc:
        sys.stdout.write(f"Error explaining source down-rank signals: {exc}\n")
        return 1

    sys.stdout.write(format_source_downrank_explanations(explanations))
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
    from output.context_memory import _project_is_curated

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
            if not args.include_non_curated:
                rows = [
                    row
                    for row in rows
                    if _project_is_curated(
                        str(row.get("project_name") or ""),
                        str(row.get("github_repo") or ""),
                    )
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


def handle_memory_diagnose_project_signals(args: argparse.Namespace) -> int:
    import json
    from output.project_signal_diagnostics import (
        diagnose_project_signal_matching,
        format_project_signal_diagnostics,
    )

    settings = load_settings()

    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")
        report = diagnose_project_signal_matching(
            settings,
            week_label=args.week,
            topic_limit=max(1, int(args.limit or 10)),
        )
    except Exception as exc:
        sys.stdout.write(f"Error diagnosing project signal matching: {exc}\n")
        return 1

    if args.json:
        sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    else:
        sys.stdout.write(format_project_signal_diagnostics(report))
    return 0


def _format_receipt_list(values: object, *, limit: int = 6) -> str:
    if not isinstance(values, list) or not values:
        return "none"
    rendered = [str(value) for value in values[:limit]]
    if len(values) > limit:
        rendered.append(f"+{len(values) - limit} more")
    return ", ".join(rendered)


def _format_receipt_dict(values: object, *, limit: int = 6) -> str:
    if not isinstance(values, dict) or not values:
        return "none"
    parts = []
    for index, (key, value) in enumerate(values.items()):
        if index >= limit:
            parts.append(f"+{len(values) - limit} more")
            break
        parts.append(f"{key}={value}")
    return ", ".join(parts)


def _format_research_brief_receipt(receipt: dict) -> str:
    source_set = receipt.get("source_set") or {}
    post_counts = receipt.get("post_counts") or {}
    config_fingerprints = receipt.get("config_fingerprints") or {}

    lines = [
        f"Receipt {receipt.get('receipt_id') or 'n/a'}",
        f"  source_of_truth: research_brief_receipts row id={receipt.get('id') or 'n/a'} plus linked digests/signal_evidence_items/llm_usage/artifacts",
        "  refresh_rule: created once after generation; delivery and verification fields update as lifecycle steps complete",
        "  retrieval_path: receipt_id, week_label, digest_id, artifact path, or Telegraph URL",
        "  debug_surface: identity, evidence window, source set, model/config fingerprints, artifacts, delivery refs, verification, health flags",
        f"  identity: week={receipt.get('week_label') or 'n/a'} digest_id={receipt.get('digest_id') or 'n/a'} generated_at={receipt.get('generated_at') or 'n/a'} source_version={receipt.get('source_version') or 'n/a'}",
        f"  evidence_window: start={receipt.get('window_start') or 'n/a'} end={receipt.get('window_end') or 'n/a'} channels={_format_receipt_list(receipt.get('included_channels'))}",
        f"  post_counts: {_format_receipt_dict(post_counts)}",
        f"  source_links: {_format_receipt_list(source_set.get('telegram_source_links'))}",
        f"  source_evidence_item_ids: {_format_receipt_list(source_set.get('source_evidence_item_ids'))}",
        f"  source_post_ids: {_format_receipt_list(source_set.get('source_post_ids'))}",
        f"  scopes: projects={_format_receipt_list(receipt.get('project_scopes'))} topics={_format_receipt_list(receipt.get('topic_scopes'))}",
        f"  broad_fallback: used={bool(source_set.get('broad_fallback_used'))} reason={source_set.get('broad_fallback_reason') or 'n/a'}",
        f"  model: provider={receipt.get('llm_provider') or 'n/a'} model={receipt.get('llm_model') or 'n/a'} category={receipt.get('llm_category') or 'n/a'} prompt={receipt.get('prompt_template_path') or 'n/a'}",
        f"  config_fingerprints: {_format_receipt_list(list(config_fingerprints.keys()))}",
        f"  artifacts: markdown={receipt.get('markdown_path') or 'n/a'} json={receipt.get('json_path') or 'n/a'} html={receipt.get('html_path') or 'n/a'}",
        f"  delivery: telegraph={receipt.get('telegraph_url') or 'n/a'} telegram_at={receipt.get('telegram_delivery_timestamp') or 'n/a'} message_id={receipt.get('telegram_message_id') or 'n/a'} fallback_used={bool(receipt.get('fallback_delivery_used'))} fallback={receipt.get('fallback_delivery') or 'n/a'}",
        f"  verification: status={receipt.get('verification_status') or 'n/a'} method={receipt.get('verifier_method') or 'n/a'} checked_at={receipt.get('checked_at') or 'n/a'} checked_by={receipt.get('checked_by') or 'n/a'}",
        f"  verifier_notes: {receipt.get('verifier_notes') or 'n/a'}",
        f"  health_flags: {_format_receipt_list(receipt.get('health_flags'))}",
    ]
    return "\n".join(lines)


def handle_memory_inspect_receipts(args: argparse.Namespace) -> int:
    from db.research_brief_receipts import fetch_research_brief_receipts

    settings = load_settings()

    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")

        with sqlite3.connect(settings.db_path) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON;")
            receipts = fetch_research_brief_receipts(
                connection,
                receipt_id=args.receipt_id,
                week_label=args.week,
                digest_id=args.digest_id,
                verification_status=args.status,
                artifact_path=args.artifact_path,
                telegraph_url=args.telegraph_url,
                limit=args.limit,
            )
    except Exception as exc:
        sys.stdout.write(f"Error inspecting Research Brief receipts: {exc}\n")
        return 1

    if not receipts:
        sys.stdout.write("No Research Brief receipts found for the given scope.\n")
        return 0

    sys.stdout.write(("\n\n".join(_format_research_brief_receipt(receipt) for receipt in receipts)).rstrip() + "\n")
    return 0


def handle_memory_inspect_core_receipt(args: argparse.Namespace) -> int:
    from db.research_brief_receipts import fetch_research_brief_receipts
    from proof_receipts import (
        build_core_research_brief_receipt,
        core_receipt_sha256,
        verify_core_research_brief_evidence_refs,
    )

    settings = load_settings()

    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")

        with sqlite3.connect(settings.db_path) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON;")
            receipts = fetch_research_brief_receipts(
                connection,
                receipt_id=args.receipt_id,
                week_label=args.week,
                digest_id=args.digest_id,
                verification_status=args.status,
                artifact_path=args.artifact_path,
                telegraph_url=args.telegraph_url,
                limit=args.limit,
            )
    except Exception as exc:
        sys.stdout.write(f"Error inspecting Core-compatible Research Brief receipt: {exc}\n")
        return 1

    if not receipts:
        sys.stdout.write("No Research Brief receipts found for the given scope.\n")
        return 0

    core_receipts = []
    for receipt in receipts:
        try:
            core_receipt = build_core_research_brief_receipt(receipt)
        except Exception as exc:
            sys.stdout.write(
                f"Error building Core-compatible receipt {receipt.get('receipt_id') or 'n/a'}: {exc}\n"
            )
            return 1
        core_receipt["receipt_sha256"] = core_receipt_sha256(core_receipt)
        if args.verify_evidence:
            core_receipt["evidence_verification"] = verify_core_research_brief_evidence_refs(
                connection,
                core_receipt,
            )
        core_receipts.append(core_receipt)

    payload: dict | list[dict]
    payload = core_receipts[0] if len(core_receipts) == 1 else core_receipts
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return 0


def handle_memory_review_receipt(args: argparse.Namespace) -> int:
    from db.research_brief_receipts import review_research_brief_receipt

    if not any([args.receipt_id, args.week, args.digest_id is not None]):
        sys.stdout.write("receipt-id, week, or digest-id is required.\n")
        return 1

    settings = load_settings()

    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")

        with sqlite3.connect(settings.db_path) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON;")
            receipt = review_research_brief_receipt(
                connection,
                receipt_id=args.receipt_id,
                week_label=args.week,
                digest_id=args.digest_id,
                verification_status=args.status,
                verifier_notes=args.notes,
                checked_by=args.checked_by,
            )
    except Exception as exc:
        sys.stdout.write(f"Error reviewing Research Brief receipt: {exc}\n")
        return 1

    if receipt is None:
        sys.stdout.write("No Research Brief receipt found for the given scope.\n")
        return 1

    lines = [
        f"Reviewed Research Brief receipt {receipt.get('receipt_id')}",
        f"status={receipt.get('verification_status')}",
        f"method={receipt.get('verifier_method')}",
        f"checked_by={receipt.get('checked_by')}",
    ]
    if receipt.get("verifier_notes"):
        lines.append(f"notes={receipt.get('verifier_notes')}")
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


def _json_list_preview(value: object, *, limit: int = 6) -> str:
    try:
        parsed = json.loads(value or "[]") if isinstance(value, str) else value
    except json.JSONDecodeError:
        parsed = []
    if not isinstance(parsed, list) or not parsed:
        return "none"
    items = [str(item) for item in parsed[:limit]]
    if len(parsed) > limit:
        items.append(f"+{len(parsed) - limit} more")
    return ", ".join(items)


def _json_dict_preview(value: object, *, limit: int = 6) -> str:
    try:
        parsed = json.loads(value or "{}") if isinstance(value, str) else value
    except json.JSONDecodeError:
        parsed = {}
    if not isinstance(parsed, dict) or not parsed:
        return "none"
    parts = []
    for index, (key, item) in enumerate(parsed.items()):
        if index >= limit:
            parts.append(f"+{len(parsed) - limit} more")
            break
        parts.append(f"{key}={item}")
    return ", ".join(parts)


def _append_channel_intelligence_claims(
    connection: sqlite3.Connection,
    lines: list[str],
    args: argparse.Namespace,
) -> None:
    clauses = []
    params: list[object] = []
    if args.week:
        clauses.append("(first_seen_week <= ? AND last_seen_week >= ?)")
        params.extend([args.week, args.week])
    if args.project:
        clauses.append("project_name = ?")
        params.append(args.project)
    if args.topic:
        clauses.append("topic_label = ?")
        params.append(args.topic)
    if args.status:
        clauses.append("status = ?")
        params.append(args.status)
    if args.channel:
        clauses.append(
            """
            id IN (
                SELECT claim_id
                FROM claim_occurrences
                WHERE source_channel = ?
            )
            """
        )
        params.append(args.channel)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = connection.execute(
        f"""
        SELECT *
        FROM channel_repeated_claims
        {where_sql}
        ORDER BY last_seen_week DESC, id DESC
        LIMIT ?
        """,
        (*params, max(1, int(args.limit or 10))),
    ).fetchall()
    lines.append(f"claims ({len(rows)}):")
    if not rows:
        lines.append("  none")
        return
    for row in rows:
        lines.append(
            f"  claim id={row['id']} status={row['status']} type={row['claim_type']} "
            f"strength={row['evidence_strength']} project={row['project_name'] or 'n/a'} topic={row['topic_label'] or 'n/a'}"
        )
        lines.append(
            f"    weeks={row['first_seen_week'] or 'n/a'}..{row['last_seen_week'] or 'n/a'} "
            f"occurrences={row['occurrence_count']} channels={row['channel_count']}"
        )
        lines.append(f"    normalized_claim: {row['normalized_claim']}")
        lines.append(f"    evidence_item_ids: {_json_list_preview(row['evidence_item_ids_json'])}")
        lines.append(f"    refresh_scope: {_json_dict_preview(row['refresh_scope_json'])}")


def _append_channel_intelligence_narratives(
    connection: sqlite3.Connection,
    lines: list[str],
    args: argparse.Namespace,
) -> None:
    clauses = []
    params: list[object] = []
    if args.week:
        clauses.append("(first_seen_week <= ? AND last_seen_week >= ?)")
        params.extend([args.week, args.week])
    if args.project:
        clauses.append("project_name = ?")
        params.append(args.project)
    if args.topic:
        clauses.append("topic_label = ?")
        params.append(args.topic)
    if args.status:
        clauses.append("status = ?")
        params.append(args.status)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = connection.execute(
        f"""
        SELECT *
        FROM channel_narratives
        {where_sql}
        ORDER BY last_seen_week DESC, id DESC
        LIMIT ?
        """,
        (*params, max(1, int(args.limit or 10))),
    ).fetchall()
    lines.append(f"narratives ({len(rows)}):")
    if not rows:
        lines.append("  none")
        return
    for row in rows:
        claim_links = connection.execute(
            """
            SELECT claim_id, shared_evidence_count, confidence
            FROM narrative_claim_links
            WHERE narrative_id = ?
            ORDER BY claim_id ASC
            LIMIT ?
            """,
            (row["id"], max(1, int(args.limit or 10))),
        ).fetchall()
        lines.append(
            f"  narrative id={row['id']} status={row['status']} project={row['project_name'] or 'n/a'} "
            f"topic={row['topic_label'] or 'n/a'}"
        )
        lines.append(f"    title: {row['title']}")
        lines.append(
            f"    support: evidence={row['supporting_post_count']} channels={row['supporting_channel_count']} "
            f"linked_claims={row['linked_claim_count']}"
        )
        lines.append(f"    evidence_item_ids: {_json_list_preview(row['evidence_item_ids_json'])}")
        lines.append(f"    source_channels: {_json_list_preview(row['source_channels_json'])}")
        lines.append(f"    refresh_scope: {_json_dict_preview(row['refresh_scope_json'])}")
        if claim_links:
            rendered_links = [
                f"claim={link['claim_id']} shared_evidence={link['shared_evidence_count']} confidence={float(link['confidence'] or 0.0):.2f}"
                for link in claim_links
            ]
            lines.append(f"    claim_links: {'; '.join(rendered_links)}")
        else:
            lines.append("    claim_links: none")


def _append_channel_intelligence_sources(
    connection: sqlite3.Connection,
    lines: list[str],
    args: argparse.Namespace,
) -> None:
    clauses = []
    params: list[object] = []
    if args.week:
        clauses.append("week_label = ?")
        params.append(args.week)
    if args.project:
        clauses.append("project_name = ?")
        params.append(args.project)
    if args.topic:
        clauses.append("topic_label = ?")
        params.append(args.topic)
    if args.channel:
        clauses.append("channel_username = ?")
        params.append(args.channel)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = connection.execute(
        f"""
        SELECT *
        FROM source_observations
        {where_sql}
        ORDER BY week_label DESC, channel_username ASC
        LIMIT ?
        """,
        (*params, max(1, int(args.limit or 10))),
    ).fetchall()
    lines.append(f"source_observations ({len(rows)}):")
    if not rows:
        lines.append("  none")
        return
    for row in rows:
        lines.append(
            f"  source id={row['id']} channel={row['channel_username']} week={row['week_label']} "
            f"scope={row['scope_key']}"
        )
        lines.append(
            "    counters: "
            f"posts={row['post_count']} scored={row['scored_count']} evidence={row['evidence_count']} "
            f"cited={row['cited_count']} acted_on={row['acted_on_count']} skipped={row['skipped_count']} "
            f"rejected={row['rejected_count']} low_signal={row['low_signal_count']} "
            f"repeated_claims={row['repeated_claim_count']} useful={row['useful_count']}"
        )
        lines.append(f"    raw_inputs: {_json_dict_preview(row['counters_json'])}")


def _append_channel_intelligence_entity_links(
    connection: sqlite3.Connection,
    lines: list[str],
    args: argparse.Namespace,
) -> None:
    clauses = []
    params: list[object] = []
    if args.week:
        clauses.append("week_label = ?")
        params.append(args.week)
    if args.project:
        clauses.append("project_name = ?")
        params.append(args.project)
    if args.topic:
        clauses.append("topic_label = ?")
        params.append(args.topic)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = connection.execute(
        f"""
        SELECT *
        FROM intelligence_entity_links
        {where_sql}
        ORDER BY week_label DESC, entity_label ASC, id DESC
        LIMIT ?
        """,
        (*params, max(1, int(args.limit or 10))),
    ).fetchall()
    lines.append(f"entity_links ({len(rows)}):")
    if not rows:
        lines.append("  none")
        return
    for row in rows:
        lines.append(
            f"  entity_link id={row['id']} label={row['entity_label']} type={row['entity_type']} "
            f"object={row['linked_object_type']}:{row['linked_object_id']} project={row['project_name'] or 'n/a'}"
        )
        lines.append(
            f"    source={row['source_table'] or 'n/a'}:{row['source_row_id'] or 'n/a'} "
            f"confidence={float(row['confidence'] or 0.0):.2f} extractor={row['extractor_version']}"
        )
        lines.append(f"    reason: {row['reason'] or 'n/a'}")


def _append_channel_intelligence_project_links(
    connection: sqlite3.Connection,
    lines: list[str],
    args: argparse.Namespace,
) -> None:
    clauses = []
    params: list[object] = []
    if args.week:
        clauses.append("week_label = ?")
        params.append(args.week)
    if args.project:
        clauses.append("project_name = ?")
        params.append(args.project)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = connection.execute(
        f"""
        SELECT *
        FROM project_intelligence_links
        {where_sql}
        ORDER BY week_label DESC, project_name ASC, linked_object_type ASC, id DESC
        LIMIT ?
        """,
        (*params, max(1, int(args.limit or 10))),
    ).fetchall()
    lines.append(f"project_links ({len(rows)}):")
    if not rows:
        lines.append("  none")
        return
    for row in rows:
        lines.append(
            f"  project_link id={row['id']} project={row['project_name']} "
            f"object={row['linked_object_type']}:{row['linked_object_id']} week={row['week_label'] or 'n/a'}"
        )
        lines.append(
            f"    score={float(row['relevance_score'] or 0.0):.2f} active_project={row['active_project']} "
            f"evidence_item_ids={_json_list_preview(row['evidence_item_ids_json'])}"
        )
        lines.append(f"    reason: {row['match_reason'] or 'n/a'}")
        lines.append(f"    refresh_scope: {_json_dict_preview(row['refresh_scope_json'])}")


def handle_memory_inspect_channel_intelligence(args: argparse.Namespace) -> int:
    settings = load_settings()

    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")

        with sqlite3.connect(settings.db_path) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON;")
            lines = [
                "Channel Intelligence inspection",
                "source_of_truth: channel_repeated_claims, claim_occurrences, channel_narratives, narrative_claim_links, source_observations, intelligence_entity_links, project_intelligence_links",
                "refresh_rule: derived rows rebuilt by output.channel_intelligence refresh helpers; canonical inputs remain posts/evidence/feedback/decisions/usefulness logs",
                "retrieval_path: week, project, topic, channel, status, and linked row IDs",
                "debug_surface: claims, occurrences, narratives, source counters, entity links, project links, refresh_scope_json, counters_json",
                (
                    "scope: "
                    f"kind={args.kind} week={args.week or 'any'} project={args.project or 'any'} "
                    f"topic={args.topic or 'any'} channel={args.channel or 'any'} status={args.status or 'any'}"
                ),
            ]
            if args.kind in {"all", "claims"}:
                _append_channel_intelligence_claims(connection, lines, args)
            if args.kind in {"all", "narratives"}:
                _append_channel_intelligence_narratives(connection, lines, args)
            if args.kind in {"all", "sources"}:
                _append_channel_intelligence_sources(connection, lines, args)
            if args.kind in {"all", "entity-links"}:
                _append_channel_intelligence_entity_links(connection, lines, args)
            if args.kind in {"all", "project-links"}:
                _append_channel_intelligence_project_links(connection, lines, args)
    except Exception as exc:
        sys.stdout.write(f"Error inspecting Channel Intelligence: {exc}\n")
        return 1

    sys.stdout.write("\n".join(lines).rstrip() + "\n")
    return 0


def handle_channel_intelligence_report(args: argparse.Namespace) -> int:
    from output.channel_intelligence_report import render_channel_intelligence_report

    settings = load_settings()

    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")

        with sqlite3.connect(settings.db_path) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON;")
            report = render_channel_intelligence_report(
                connection,
                week_label=args.week,
                project_name=args.project,
                topic_label=args.topic,
                limit=args.limit,
            )
    except Exception as exc:
        sys.stdout.write(f"Error rendering Channel Intelligence report: {exc}\n")
        return 1

    sys.stdout.write(report)
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
