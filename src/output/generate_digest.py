import json
import logging
import os
import re
import sqlite3
import time
from dataclasses import asdict
from datetime import timezone, date, datetime, timedelta
from hashlib import sha256
from pathlib import Path

from config.settings import PROJECT_ROOT, Settings
from db.research_brief_receipts import (
    record_research_brief_receipt,
    update_research_brief_receipt_delivery_refs,
)
from llm.client import complete
from llm.router import route
from output import generate_recommendations as recommendations_module
from output.render_report import write_report_html
from output.report_quality import (
    ReportQualityFinding,
    format_findings_for_notification,
    format_finding_for_log,
    validate_weekly_artifacts,
)
from output.signal_report import format_signal_report
from output.weekly_messages import build_brief_message, write_weekly_message
from proof_receipts import (
    build_core_research_brief_receipt,
    core_receipt_sha256,
    summarize_research_brief_evidence,
)
from output.report_schema import (
    DigestResult,
    EvidenceItem,
    KeyFinding,
    ReportMeta,
    ReportSection,
    ResearchReport,
)
from output.report_utils import _extract_markdown_section
from processing.score_posts import score_posts

try:
    from bot.callbacks import build_artifact_feedback_markup
    from bot.telegram_delivery import send_document, send_text
except ImportError:  # pragma: no cover
    from src.bot.callbacks import build_artifact_feedback_markup
    from src.bot.telegram_delivery import send_document, send_text

try:
    from delivery.telegraph import publish_article
except ImportError:  # pragma: no cover
    from src.delivery.telegraph import publish_article

try:
    from integrations.github_crossref import NO_OVERLAP_NOTE, crossref_repos_to_topics
    from integrations.github_sync import sync_github_projects
except Exception:  # pragma: no cover
    NO_OVERLAP_NOTE = "active this week, no Telegram overlap found"
    crossref_repos_to_topics = None
    sync_github_projects = None


LOGGER = logging.getLogger(__name__)
PROMPT_PATH = PROJECT_ROOT / "docs" / "prompts" / "digest_generation.md"
OUTPUT_DIR = PROJECT_ROOT / "data" / "output" / "digests"
STUDY_PLAN_OUTPUT_DIR = PROJECT_ROOT / "data" / "output" / "study_plans"
PROJECT_INSIGHTS_OUTPUT_DIR = PROJECT_ROOT / "data" / "output" / "project_insights"
TEXT_EXCERPT_LENGTH = 250
MAX_STRONG = 3
MAX_WATCH = 3
MAX_CULTURAL = 1
MAX_OUTPUT_WORDS = 600
LOW_SIGNAL_MIN_ACTIONABLE = 1
CONFIG_FINGERPRINT_PATHS = {
    "scoring_config": PROJECT_ROOT / "src" / "config" / "scoring.yaml",
    "profile_config": PROJECT_ROOT / "src" / "config" / "profile.yaml",
    "projects_config": PROJECT_ROOT / "src" / "config" / "projects.yaml",
    "channels_config": PROJECT_ROOT / "src" / "config" / "channels.yaml",
    "prompt_template": PROMPT_PATH,
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat().replace("+00:00", "Z")


def _compute_week_label(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    year, week, _ = current.isocalendar()
    return f"{year}-W{week:02d}"


def _format_date_range(week_label: str) -> str:
    year_str, week_str = week_label.split("-W", maxsplit=1)
    week_start = date.fromisocalendar(int(year_str), int(week_str), 1)
    week_end = date.fromisocalendar(int(year_str), int(week_str), 7)
    if week_start.year == week_end.year:
        if week_start.month == week_end.month:
            return f"{week_start.strftime('%B')} {week_start.day}-{week_end.day}, {week_start.year}"
        return (
            f"{week_start.strftime('%B')} {week_start.day}-"
            f"{week_end.strftime('%B')} {week_end.day}, {week_start.year}"
        )
    return (
        f"{week_start.strftime('%B')} {week_start.day}, {week_start.year}-"
        f"{week_end.strftime('%B')} {week_end.day}, {week_end.year}"
    )


def _load_prompt_sections() -> tuple[str, str]:
    prompt_markdown = PROMPT_PATH.read_text(encoding="utf-8")
    system_prompt = _extract_markdown_section(prompt_markdown, "System Prompt")
    user_template = _extract_markdown_section(prompt_markdown, "User Prompt Template")
    return system_prompt, user_template


def _make_excerpt(text: str | None) -> str:
    compact = " ".join((text or "").split())
    return compact[:TEXT_EXCERPT_LENGTH]


def _count_words(text: str) -> int:
    return len(text.split())


def _write_digest_file(week_label: str, content_md: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{week_label}.md"
    output_path.write_text(content_md, encoding="utf-8")
    return output_path


def _write_copyable_digest_file(week_label: str, content_md: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{week_label}_copy.txt"
    output_path.write_text(content_md, encoding="utf-8")
    return output_path


def _send_copyable_digest_document(chat_id: str, week_label: str, content_md: str, token: str) -> None:
    try:
        copy_path = _write_copyable_digest_file(week_label, content_md)
        send_document(
            chat_id=chat_id,
            file_path=str(copy_path),
            caption=f"Copyable Research Brief {week_label}",
            token=token,
        )
    except Exception:
        LOGGER.warning("Failed to send copyable research brief week=%s", week_label, exc_info=True)


def _write_digest_json_file(week_label: str, report: ResearchReport) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{week_label}.json"
    output_path.write_text(json.dumps(asdict(report), ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def _send_digest_to_telegram_owner(content_md: str, week_label: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_OWNER_CHAT_ID", "").strip()
    if not token or not chat_id:
        return
    send_text(chat_id=chat_id, text=content_md, token=token)
    LOGGER.info("Digest sent to Telegram owner week=%s", week_label)


def _extract_actions_this_week_count(content_md: str | None) -> int:
    in_actions = False
    count = 0
    for raw_line in str(content_md or "").splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            in_actions = line == "## Actions This Week"
            continue
        if in_actions and re.match(r"^\d+\.\s+", line):
            count += 1
    return count


def _build_review_notification(
    week_label: str,
    strong_count: int,
    watch_count: int,
    *,
    post_count: int | None = None,
    noise_count: int | None = None,
    action_count: int | None = None,
    evidence_summary_note: str | None = None,
) -> str:
    if post_count is not None and action_count is not None:
        funnel = f"{post_count} posts -> {strong_count} strong / {watch_count} watch"
        if noise_count is not None:
            funnel = f"{funnel} / {noise_count} noise"
        funnel = f"{funnel} -> {action_count} actions"
    else:
        funnel = f"{strong_count} strong signals, {watch_count} watch"
    lines = [
        f"Research Brief {week_label} is ready.",
        f"Funnel: {funnel}.",
    ]
    if evidence_summary_note:
        lines.append(evidence_summary_note)
    lines.append("Open the full brief:")
    return "\n".join(lines)[:520]


def _build_receipt_audit_note(receipt: dict | None) -> str | None:
    if not receipt:
        return None
    status = str(receipt.get("verification_status") or "pending")
    flags = [str(flag) for flag in receipt.get("health_flags", []) if str(flag).strip()]
    fallback_used = bool(receipt.get("fallback_delivery_used"))
    core_hash = _build_core_receipt_hash(receipt)
    if status == "pending" and not flags and not fallback_used and not core_hash:
        return None

    parts = [f"Receipt: {status}"]
    if core_hash:
        parts.append(f"core_sha256={core_hash}")
    if flags:
        parts.append(f"flags={', '.join(flags[:4])}")
    if fallback_used:
        parts.append(f"fallback={receipt.get('fallback_delivery') or 'yes'}")
    return " | ".join(parts)[:220]


def _format_receipt_top_channels(summary: dict) -> str:
    channels = summary.get("top_channels") or []
    if not channels:
        return "no channel concentration"
    parts = []
    for item in channels[:3]:
        channel = str(item.get("channel") or "").strip()
        count = int(item.get("count") or 0)
        if channel:
            parts.append(f"{channel} ({count})")
    return "top channels: " + ", ".join(parts) if parts else "no channel concentration"


def _format_receipt_delivery_status(summary: dict) -> str:
    if summary.get("fallback_delivery_used"):
        return f"fallback used: {summary.get('fallback_delivery') or 'yes'}"
    return "fallback not used"


def _format_receipt_evidence_section(summary: dict | None) -> str | None:
    if not summary:
        return None
    status = str(summary.get("status") or "needs_review")
    local_rows = int(summary.get("local_evidence_row_count") or 0)
    source_links = int(summary.get("telegram_source_link_count") or 0)
    confidence = str(summary.get("confidence_sentence") or "needs review")
    lines = [
        "## Evidence & Source Mix",
        (
            f"- Evidence: {local_rows} local evidence rows, {source_links} linked Telegram "
            f"sources; receipt lookup {status}."
        ),
        f"- Source mix: Telegram-first; {_format_receipt_top_channels(summary)}.",
        f"- Delivery: {_format_receipt_delivery_status(summary)}.",
        f"- Confidence: {confidence}",
    ]
    failures = [str(item) for item in summary.get("failures", []) if str(item).strip()]
    review_notes = [str(item) for item in summary.get("review_notes", []) if str(item).strip()]
    if failures:
        lines.append(f"- Review: {failures[0]}")
    elif review_notes:
        lines.append(f"- Review: {review_notes[0]}")
    return "\n".join(lines)


def _format_receipt_evidence_notification(summary: dict | None) -> str | None:
    if not summary:
        return None
    status = str(summary.get("status") or "needs_review")
    confidence = str(summary.get("confidence_level") or "needs_review")
    local_rows = int(summary.get("local_evidence_row_count") or 0)
    source_links = int(summary.get("telegram_source_link_count") or 0)
    delivery = ""
    if summary.get("fallback_delivery_used"):
        delivery = f"; fallback={summary.get('fallback_delivery') or 'yes'}"
    return (
        f"Evidence: {local_rows} local rows, {source_links} Telegram links, "
        f"lookup {status}, confidence {confidence}{delivery}."
    )[:240]


def _upsert_evidence_summary_section(content_md: str, summary: dict | None) -> str:
    section = _format_receipt_evidence_section(summary)
    if not section:
        return content_md

    heading = "## Evidence & Source Mix"
    lines = content_md.rstrip().splitlines()
    section_lines = section.splitlines()

    start = next((index for index, line in enumerate(lines) if line.strip() == heading), None)
    if start is not None:
        end = next(
            (index for index in range(start + 1, len(lines)) if lines[index].startswith("## ")),
            len(lines),
        )
        updated = [*lines[:start], *section_lines, "", *lines[end:]]
        return "\n".join(updated).strip() + "\n"

    insert_at = len(lines)
    what_changed = next((index for index, line in enumerate(lines) if line.strip() == "## What Changed"), None)
    if what_changed is not None:
        insert_at = next(
            (index for index in range(what_changed + 1, len(lines)) if lines[index].startswith("## ")),
            len(lines),
        )
    else:
        decision_brief = next((index for index, line in enumerate(lines) if line.strip() == "## Decision Brief"), None)
        if decision_brief is not None:
            insert_at = next(
                (index for index in range(decision_brief + 1, len(lines)) if lines[index].startswith("## ")),
                len(lines),
            )

    updated = [*lines[:insert_at], "", *section_lines, "", *lines[insert_at:]]
    return "\n".join(updated).strip() + "\n"


def _build_core_receipt_hash(receipt: dict) -> str | None:
    try:
        return core_receipt_sha256(build_core_research_brief_receipt(receipt))
    except ValueError as exc:
        LOGGER.info(
            "Core-compatible receipt unavailable receipt_id=%s reason=%s",
            receipt.get("receipt_id") or "n/a",
            exc,
        )
        return None
    except Exception:
        LOGGER.warning(
            "Failed to build Core-compatible receipt hash receipt_id=%s",
            receipt.get("receipt_id") or "n/a",
            exc_info=True,
        )
        return None


def _build_digest_health_alert(
    week_label: str,
    *,
    post_count: int,
    strong_count: int,
    watch_count: int,
    channel_count: int = 0,
    topic_count: int = 0,
) -> str | None:
    actionable_count = strong_count + watch_count
    if post_count <= 0:
        return (
            f"Research pipeline alert {week_label}\n"
            "No Telegram posts were available for the last 7 days.\n"
            "Check ingestion credentials, active channels, and service schedule."
        )[:300]
    if actionable_count < LOW_SIGNAL_MIN_ACTIONABLE:
        return (
            f"Research pipeline alert {week_label}\n"
            f"{post_count} posts from {channel_count} channels, but 0 strong/watch signals.\n"
            f"Topics: {topic_count}. Check scoring thresholds, reaction feedback, and channel quality."
        )[:300]
    return None


def _read_optional_artifact(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8") if path.exists() else None
    except OSError:
        LOGGER.warning("Failed to read artifact for report-quality validation path=%s", path, exc_info=True)
        return None


def _validate_weekly_report_quality(
    *,
    week_label: str,
    content_md: str,
    post_count: int,
    strong_count: int,
    watch_count: int,
    cultural_count: int,
    noise_count: int,
    project_match_count: int = 0,
    output_word_count: int = 0,
) -> list[ReportQualityFinding]:
    try:
        findings = validate_weekly_artifacts(
            week_label=week_label,
            digest_md=content_md,
            study_plan_md=_read_optional_artifact(STUDY_PLAN_OUTPUT_DIR / f"{week_label}.md"),
            project_insights_md=_read_optional_artifact(PROJECT_INSIGHTS_OUTPUT_DIR / f"{week_label}.md"),
            facts={
                "week_label": week_label,
                "post_count": post_count,
                "strong_count": strong_count,
                "watch_count": watch_count,
                "cultural_count": cultural_count,
                "noise_count": noise_count,
                "project_match_count": project_match_count,
                "output_word_count": output_word_count,
            },
        )
    except Exception:
        LOGGER.warning("Report-quality validation failed week=%s", week_label, exc_info=True)
        return []

    for finding in findings:
        log_method = LOGGER.error if finding.severity == "critical" else LOGGER.warning
        log_method("Report quality finding week=%s %s", week_label, format_finding_for_log(finding))
    return findings


def _path_fingerprint(path: Path) -> dict[str, str]:
    try:
        content = path.read_bytes()
    except OSError:
        return {"path": str(path.relative_to(PROJECT_ROOT)), "status": "missing"}
    return {
        "path": str(path.relative_to(PROJECT_ROOT)),
        "sha256": sha256(content).hexdigest(),
    }


def _build_config_fingerprints() -> dict[str, dict[str, str]]:
    return {
        name: _path_fingerprint(path)
        for name, path in CONFIG_FINGERPRINT_PATHS.items()
    }


def _source_version() -> str | None:
    for env_name in ("GIT_COMMIT", "SOURCE_VERSION", "RENDER_GIT_COMMIT"):
        value = os.environ.get(env_name, "").strip()
        if value:
            return value
    return None


def _parse_json_list_text(value: str | None) -> list:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _generation_params_fingerprint() -> str:
    params = {
        "max_strong": MAX_STRONG,
        "max_watch": MAX_WATCH,
        "max_cultural": MAX_CULTURAL,
        "max_output_words": MAX_OUTPUT_WORDS,
        "low_signal_min_actionable": LOW_SIGNAL_MIN_ACTIONABLE,
    }
    encoded = json.dumps(params, sort_keys=True).encode("utf-8")
    return sha256(encoded).hexdigest()


def _load_delivery_state(connection: sqlite3.Connection, week_label: str) -> dict[str, str]:
    row = connection.execute(
        """
        SELECT COALESCE(telegraph_url, '') AS telegraph_url,
               COALESCE(telegram_sent_at, '') AS telegram_sent_at
        FROM digests
        WHERE week_label = ?
        LIMIT 1
        """,
        (week_label,),
    ).fetchone()
    if row is None:
        return {"telegraph_url": "", "telegram_sent_at": ""}
    return {
        "telegraph_url": str(row["telegraph_url"] or ""),
        "telegram_sent_at": str(row["telegram_sent_at"] or ""),
    }


def _mark_delivery_state(
    connection: sqlite3.Connection,
    week_label: str,
    *,
    telegraph_url: str | None = None,
    telegram_sent_at: str | None = None,
) -> None:
    fields: list[str] = []
    params: list[str] = []
    if telegraph_url is not None:
        fields.append("telegraph_url = ?")
        params.append(telegraph_url)
    if telegram_sent_at is not None:
        fields.append("telegram_sent_at = ?")
        params.append(telegram_sent_at)
    if not fields:
        return
    params.append(week_label)
    connection.execute(
        f"UPDATE digests SET {', '.join(fields)} WHERE week_label = ?",
        params,
    )


def _mark_receipt_delivery_state(
    connection: sqlite3.Connection,
    *,
    week_label: str,
    digest_id: int | None = None,
    telegraph_url: str | None = None,
    telegram_delivery_timestamp: str | None = None,
    telegram_message_id: int | None = None,
    fallback_delivery: str | None = None,
    fallback_delivery_used: bool | None = None,
    health_flags: list[str] | None = None,
) -> None:
    try:
        updated = update_research_brief_receipt_delivery_refs(
            connection,
            week_label=week_label if digest_id is None else None,
            digest_id=digest_id,
            telegraph_url=telegraph_url,
            telegram_delivery_timestamp=telegram_delivery_timestamp,
            telegram_message_id=telegram_message_id,
            fallback_delivery=fallback_delivery,
            fallback_delivery_used=fallback_delivery_used,
            health_flags=health_flags,
        )
        if updated is None:
            LOGGER.info("Research brief receipt delivery update skipped week=%s; no receipt found", week_label)
    except Exception:
        LOGGER.warning("Failed to update research brief receipt delivery refs week=%s", week_label, exc_info=True)


def _send_weekly_review_to_telegram_owner(
    connection: sqlite3.Connection,
    content_md: str,
    week_label: str,
    strong_count: int,
    watch_count: int,
    html_path: Path | None,
    digest_id: int | None = None,
    post_count: int | None = None,
    noise_count: int | None = None,
    force_delivery: bool = False,
    health_alert: str | None = None,
    receipt_audit_note: str | None = None,
    evidence_summary_note: str | None = None,
    evidence_summary: dict | None = None,
    report_quality_warning: str | None = None,
    operator_message: str | None = None,
) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_OWNER_CHAT_ID", "").strip()
    if not token or not chat_id:
        return

    delivery_state = _load_delivery_state(connection, week_label)
    if delivery_state["telegram_sent_at"] and not force_delivery:
        _mark_receipt_delivery_state(
            connection,
            week_label=week_label,
            digest_id=digest_id,
            telegraph_url=delivery_state["telegraph_url"] or None,
            telegram_delivery_timestamp=delivery_state["telegram_sent_at"] or None,
        )
        LOGGER.info("Weekly review delivery skipped week=%s because it was already sent", week_label)
        return

    notification = operator_message or _build_review_notification(
        week_label,
        strong_count,
        watch_count,
        post_count=post_count,
        noise_count=noise_count,
        action_count=_extract_actions_this_week_count(content_md),
        evidence_summary_note=evidence_summary_note,
    )
    if health_alert and not operator_message:
        notification = f"{health_alert}\n\n{notification}"[:700]
    if report_quality_warning and not operator_message:
        notification = f"{report_quality_warning}\n\n{notification}"[:900]
    if receipt_audit_note and not operator_message:
        notification = f"{notification}\n{receipt_audit_note}"[:900]
    feedback_markup = build_artifact_feedback_markup(week_label, "research_brief")

    # Try Telegraph first
    if html_path is not None:
        try:
            html_content = html_path.read_text(encoding="utf-8")
            url = publish_article(title=f"Research Brief {week_label}", html_content=html_content)
            delivery_text = f"{notification}\n\nПолный audit-отчет: {url}" if operator_message else f"{notification}\n{url}"
            message_id = send_text(
                chat_id=chat_id,
                text=delivery_text[:4096],
                token=token,
                parse_mode=None,
                reply_markup=feedback_markup,
            )
            _send_copyable_digest_document(chat_id, week_label, content_md, token)
            sent_at = _utc_now_iso()
            _mark_delivery_state(connection, week_label, telegraph_url=url, telegram_sent_at=sent_at)
            _mark_receipt_delivery_state(
                connection,
                week_label=week_label,
                digest_id=digest_id,
                telegraph_url=url,
                telegram_delivery_timestamp=sent_at,
                telegram_message_id=message_id,
                fallback_delivery_used=False,
            )
            connection.commit()
            LOGGER.info("Weekly review published to Telegraph week=%s url=%s", week_label, url)
            return
        except Exception:
            LOGGER.warning(
                "Failed to publish Telegraph article week=%s; falling back to HTML attachment",
                week_label,
                exc_info=True,
            )

    fallback_route = "html_attachment" if html_path is not None else "text"
    if evidence_summary:
        fallback_summary = {
            **evidence_summary,
            "fallback_delivery_used": True,
            "fallback_delivery": fallback_route,
        }
        fallback_summary_note = _format_receipt_evidence_notification(fallback_summary)
        if not operator_message:
            if evidence_summary_note and fallback_summary_note:
                notification = notification.replace(evidence_summary_note, fallback_summary_note)
            elif fallback_summary_note:
                notification = f"{notification}\n{fallback_summary_note}"[:900]
        content_md = _upsert_evidence_summary_section(content_md, fallback_summary)
        try:
            _write_digest_file(week_label, content_md)
            connection.execute(
                "UPDATE digests SET content_md = ? WHERE week_label = ?",
                (content_md, week_label),
            )
        except Exception:
            LOGGER.warning("Failed to update fallback evidence summary week=%s", week_label, exc_info=True)

    message_id = send_text(
        chat_id=chat_id,
        text=notification[:4096],
        token=token,
        parse_mode=None,
        reply_markup=feedback_markup,
    )
    _send_copyable_digest_document(chat_id, week_label, content_md, token)
    sent_at = _utc_now_iso()
    _mark_delivery_state(connection, week_label, telegram_sent_at=sent_at)
    fallback_flags = ["fallback_delivery"]
    if html_path is None:
        fallback_flags.append("artifact_missing")
    _mark_receipt_delivery_state(
        connection,
        week_label=week_label,
        digest_id=digest_id,
        telegram_delivery_timestamp=sent_at,
        telegram_message_id=message_id,
        fallback_delivery=fallback_route,
        fallback_delivery_used=True,
        health_flags=fallback_flags,
    )
    connection.commit()

    if html_path is None:
        return

    try:
        send_document(
            chat_id=chat_id,
            file_path=str(html_path),
            caption=f"Research Brief {week_label}",
            token=token,
        )
        LOGGER.info("Weekly review sent to Telegram owner week=%s file=%s", week_label, html_path)
    except Exception:
        LOGGER.warning("Failed to send HTML review week=%s; falling back to text send", week_label, exc_info=True)
        send_text(chat_id=chat_id, text=content_md, token=token, parse_mode=None)
        _mark_receipt_delivery_state(
            connection,
            week_label=week_label,
            digest_id=digest_id,
            fallback_delivery="text_after_html_failure",
            fallback_delivery_used=True,
            health_flags=["fallback_delivery"],
        )


def _append_github_section(content_md: str, settings: Settings) -> str:
    """Append project × Telegram cross-reference. Omit repos with no real matches."""
    if not os.environ.get("GITHUB_USERNAME"):
        return content_md
    if sync_github_projects is None or crossref_repos_to_topics is None:
        LOGGER.warning("GitHub integrations unavailable; skipping digest GitHub section")
        return content_md

    try:
        repos = sync_github_projects(settings.db_path)
        if not repos:
            return content_md
        topic_matches = crossref_repos_to_topics(repos, settings.db_path)
    except Exception:
        LOGGER.warning("GitHub digest section skipped due to integration failure", exc_info=True)
        return content_md

    lines = ["", "## Your Projects × Telegram", ""]
    any_match = False
    for repo in repos:
        repo_name = repo["name"]
        github_repo = repo.get("github_repo") or repo_name
        commits_label = (
            f"{int(repo.get('weekly_commits') or 0)} commits this week"
            if int(repo.get("weekly_commits") or 0) > 0
            else "no activity"
        )
        matched_topics = topic_matches.get(repo_name, [])
        # Skip repos with no overlap — showing "no overlap found" adds no value
        if not matched_topics or matched_topics == [NO_OVERLAP_NOTE]:
            continue
        any_match = True
        match_label = ", ".join(matched_topics)
        lines.append(f"- [{repo_name}](https://github.com/{github_repo}) — {commits_label} — {match_label}")

    if not any_match:
        return content_md
    return content_md.rstrip() + "\n\n" + "\n".join(lines).strip() + "\n"


def _fetch_scored_posts(connection: sqlite3.Connection, cutoff_iso: str) -> dict:
    """
    Fetch posts from the last 7 days grouped by bucket.
    Returns {
      'strong': [...], 'watch': [...], 'cultural': [...], 'noise': [...],
      'all_post_count': int, 'channel_count': int, 'topic_counts': {label: count}
    }
    """
    rows = connection.execute(
        """
        SELECT
            posts.id,
            posts.channel_username,
            posts.content,
            posts.posted_at,
            posts.signal_score,
            posts.bucket,
            posts.routed_model,
            posts.score_breakdown,
            posts.project_matches,
            COALESCE(raw_posts.view_count, 0) AS view_count,
            raw_posts.message_url,
            topics.label AS topic_label
        FROM posts
        INNER JOIN raw_posts ON raw_posts.id = posts.raw_post_id
        LEFT JOIN post_topics ON post_topics.post_id = posts.id
        LEFT JOIN topics ON topics.id = post_topics.topic_id
        WHERE posts.posted_at >= ?
        ORDER BY posts.posted_at DESC, posts.id DESC
        """,
        (cutoff_iso,),
    ).fetchall()

    # Deduplicate (post may appear multiple times due to LEFT JOIN on topics)
    seen: dict[int, sqlite3.Row] = {}
    topic_by_post: dict[int, str] = {}
    topic_counts: dict[str, int] = {}

    for row in rows:
        post_id = row["id"]
        if post_id not in seen:
            seen[post_id] = row
        label = row["topic_label"] or "Unlabeled"
        if post_id not in topic_by_post:
            topic_by_post[post_id] = label
        topic_counts[label] = topic_counts.get(label, 0) + 1

    buckets: dict[str, list[dict]] = {"strong": [], "watch": [], "cultural": [], "noise": []}
    bucket_counts: dict[str, int] = {"strong": 0, "watch": 0, "cultural": 0, "noise": 0}
    total_signal_score = 0.0
    project_match_count = 0
    for post_id, row in seen.items():
        bucket = row["bucket"] or "noise"
        if bucket not in bucket_counts:
            bucket = "noise"
        bucket_counts[bucket] += 1
        total_signal_score += float(row["signal_score"] or 0.0)
        project_matches = (row["project_matches"] or "").strip()
        if project_matches and project_matches not in {"[]", "null"}:
            project_match_count += 1
        project_match_list = _parse_json_list_text(project_matches)
        entry = {
            "id": post_id,
            "channel_username": row["channel_username"],
            "content": row["content"] or "",
            "text_excerpt": _make_excerpt(row["content"]),
            "view_count": int(row["view_count"] or 0),
            "message_url": row["message_url"] or "",
            "topic_label": topic_by_post.get(post_id, "Unlabeled"),
            "signal_score": round(float(row["signal_score"] or 0.0), 4),
            "bucket": bucket,
            "routed_model": row["routed_model"] or "",
            "score_breakdown": row["score_breakdown"] or "",
            "project_matches": project_match_list,
            "posted_at": row["posted_at"],
        }
        buckets[bucket].append(entry)

    # Preserve full bucket lists for signal-first reporting and metrics.
    full_buckets = {
        bucket_name: list(entries)
        for bucket_name, entries in buckets.items()
    }

    # Sort each bucket by signal_score DESC, apply caps for prompt payload size.
    for bucket_name in ("strong", "watch", "cultural"):
        buckets[bucket_name].sort(key=lambda x: x["signal_score"], reverse=True)
    buckets["strong"] = buckets["strong"][:MAX_STRONG]
    buckets["watch"] = buckets["watch"][:MAX_WATCH]
    buckets["cultural"] = buckets["cultural"][:MAX_CULTURAL]

    return {
        **buckets,
        "all_post_count": len(seen),
        "channel_count": len({row["channel_username"] for row in seen.values()}),
        "included_channels": sorted({str(row["channel_username"]) for row in seen.values() if row["channel_username"]}),
        "topic_counts": topic_counts,
        "topic_by_post": topic_by_post,
        "bucket_counts": bucket_counts,
        "avg_signal_score": (total_signal_score / len(seen)) if seen else None,
        "project_match_count": project_match_count,
        "full_buckets": full_buckets,
    }


def _build_noise_summary(noise_posts: list[dict], topic_counts: dict[str, int]) -> str:
    """
    Summarise the noise bucket for the "Filtered Out" section.
    Returns e.g. "AI video generation (67), generic model announcements (28), memes (14)"
    """
    if not noise_posts:
        return "no significant noise this week"
    # Count noise posts by topic
    noise_by_topic: dict[str, int] = {}
    for post in noise_posts:
        label = post.get("topic_label", "Other")
        noise_by_topic[label] = noise_by_topic.get(label, 0) + 1
    top_noise = sorted(noise_by_topic.items(), key=lambda x: -x[1])[:4]
    parts = [f"{label} ({count})" for label, count in top_noise]
    return ", ".join(parts)


def _build_scored_posts_for_prompt(buckets: dict) -> list[dict]:
    """Flatten strong + watch posts into a single list for the LLM prompt."""
    posts = []
    for bucket_name in ("strong", "watch", "cultural"):
        for p in buckets[bucket_name]:
            posts.append({
                "post_id": p["id"],
                "bucket": bucket_name,
                "channel": p["channel_username"],
                "text_excerpt": p["text_excerpt"],
                "view_count": p["view_count"],
                "url": p["message_url"],
                "topic": p["topic_label"],
                "signal_score": p["signal_score"],
            })
    return posts


def _iter_receipt_source_posts(buckets: dict) -> list[dict]:
    full_buckets = buckets.get("full_buckets", {})
    posts: list[dict] = []
    seen_ids: set[int] = set()
    for bucket_name in ("strong", "watch", "cultural", "noise"):
        for post in full_buckets.get(bucket_name, buckets.get(bucket_name, [])):
            post_id = int(post.get("id") or 0)
            if post_id <= 0 or post_id in seen_ids:
                continue
            seen_ids.add(post_id)
            posts.append(post)
    return posts


def _fetch_receipt_evidence_item_ids(
    connection: sqlite3.Connection,
    *,
    week_label: str,
    post_ids: list[int],
) -> list[int]:
    if not post_ids:
        return []
    placeholders = ",".join("?" for _ in post_ids)
    try:
        rows = connection.execute(
            f"""
            SELECT id
            FROM signal_evidence_items
            WHERE week_label = ?
              AND post_id IN ({placeholders})
            ORDER BY id
            """,
            (week_label, *post_ids),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [int(row["id"] if isinstance(row, sqlite3.Row) else row[0]) for row in rows]


def _build_receipt_source_set(
    connection: sqlite3.Connection,
    *,
    week_label: str,
    source_posts: list[dict],
) -> dict:
    post_ids = [int(post.get("id") or 0) for post in source_posts if int(post.get("id") or 0) > 0]
    source_links = sorted({
        str(post.get("message_url") or "").strip()
        for post in source_posts
        if str(post.get("message_url") or "").strip()
    })
    channels = sorted({
        str(post.get("channel_username") or "").strip()
        for post in source_posts
        if str(post.get("channel_username") or "").strip()
    })
    return {
        "channels": channels,
        "telegram_source_links": source_links,
        "source_evidence_item_ids": _fetch_receipt_evidence_item_ids(
            connection,
            week_label=week_label,
            post_ids=post_ids,
        ),
        "source_post_ids": sorted(set(post_ids)),
        "broad_fallback_used": False,
    }


def _build_receipt_health_flags(
    *,
    post_count: int,
    strong_count: int,
    watch_count: int,
    markdown_path: Path | None,
    json_path: Path | None,
    html_path: Path | None,
) -> list[str]:
    flags: list[str] = []
    if post_count <= 0:
        flags.append("empty_week_alert")
    elif strong_count + watch_count < LOW_SIGNAL_MIN_ACTIONABLE:
        flags.append("low_signal_alert")

    expected_paths = [markdown_path, html_path]
    if post_count > 0:
        expected_paths.append(json_path)
    if any(path is None for path in expected_paths):
        flags.append("artifact_missing")
    return flags


def _create_research_brief_receipt(
    connection: sqlite3.Connection,
    *,
    week_label: str,
    generated_at: str,
    window_start: str,
    window_end: str,
    buckets: dict,
    digest_id: int,
    markdown_path: Path,
    json_path: Path | None,
    html_path: Path | None,
    llm_provider: str | None,
    llm_model: str | None,
    llm_category: str | None,
) -> dict:
    source_posts = _iter_receipt_source_posts(buckets)
    project_scopes = sorted({
        str(project)
        for post in source_posts
        for project in post.get("project_matches", [])
        if str(project).strip()
    })
    topic_scopes = sorted(str(topic) for topic in buckets.get("topic_counts", {}) if str(topic).strip())
    bucket_counts = buckets.get("bucket_counts", {})
    strong_count = int(bucket_counts.get("strong") or 0)
    watch_count = int(bucket_counts.get("watch") or 0)
    post_count = int(buckets.get("all_post_count") or 0)
    config_fingerprints = _build_config_fingerprints()

    return record_research_brief_receipt(
        connection,
        week_label=week_label,
        generated_at=generated_at,
        source_version=_source_version(),
        window_start=window_start,
        window_end=window_end,
        included_channels=buckets.get("included_channels", []),
        post_counts={
            "total_posts": post_count,
            "post_count_scored": post_count,
            "strong_count": strong_count,
            "watch_count": watch_count,
            "cultural_count": int(bucket_counts.get("cultural") or 0),
            "noise_count": int(bucket_counts.get("noise") or 0),
        },
        source_set=_build_receipt_source_set(
            connection,
            week_label=week_label,
            source_posts=source_posts,
        ),
        project_scopes=project_scopes,
        topic_scopes=topic_scopes,
        llm_provider=llm_provider,
        llm_model=llm_model,
        llm_category=llm_category,
        prompt_template_path=str(PROMPT_PATH.relative_to(PROJECT_ROOT)),
        prompt_template_version=config_fingerprints["prompt_template"].get("sha256"),
        config_fingerprints=config_fingerprints,
        generation_params_fingerprint=_generation_params_fingerprint(),
        digest_id=digest_id,
        markdown_path=str(markdown_path),
        json_path=str(json_path) if json_path is not None else None,
        html_path=str(html_path) if html_path is not None else None,
        verification_status="pending",
        health_flags=_build_receipt_health_flags(
            post_count=post_count,
            strong_count=strong_count,
            watch_count=watch_count,
            markdown_path=markdown_path,
            json_path=json_path,
            html_path=html_path,
        ),
    )


def _build_research_report(
    week_label: str,
    date_range: str,
    generated_at: str,
    post_count: int,
    channel_count: int,
    content_md: str,
    top_topics: list[dict],
    scored_posts_flat: list[dict],
) -> ResearchReport:
    return ResearchReport(
        meta=ReportMeta(
            week_label=week_label,
            date_range=date_range,
            generated_at=generated_at,
            post_count=post_count,
            channel_count=channel_count,
        ),
        executive_summary=[],
        key_findings=[
            KeyFinding(
                title=str(topic["label"]),
                body=f"{int(topic['post_count'])} posts captured this week.",
                evidence_ids=[],
            )
            for topic in top_topics
        ],
        sections=[ReportSection(heading="Intelligence Briefing", body=content_md)],
        evidence=[
            EvidenceItem(
                id=f"S{idx}",
                channel=str(p["channel"]),
                date="",
                excerpt=str(p["text_excerpt"]),
                url=str(p["url"]),
            )
            for idx, p in enumerate(scored_posts_flat, start=1)
        ],
        project_relevance=[],
        confidence_notes=(
            "This briefing reflects the last 7 days of ingested Telegram posts, "
            "filtered by personal relevance scoring. Only strong and watch-bucket posts "
            "were passed to synthesis."
        ),
    )


def _store_digest(
    connection: sqlite3.Connection,
    week_label: str,
    content_md: str,
    content_json: str,
    pdf_path: str | None,
    post_count: int,
) -> int:
    connection.execute(
        """
        INSERT INTO digests (week_label, generated_at, content_md, content_json, pdf_path, post_count)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(week_label) DO UPDATE SET
            generated_at = excluded.generated_at,
            content_md = excluded.content_md,
            content_json = excluded.content_json,
            pdf_path = excluded.pdf_path,
            post_count = excluded.post_count
        """,
        (week_label, _utc_now_iso(), content_md, content_json, pdf_path, post_count),
    )
    row = connection.execute(
        "SELECT id FROM digests WHERE week_label = ?",
        (week_label,),
    ).fetchone()
    if row is None:
        raise RuntimeError("digest insert could not be read back")
    return int(row["id"] if isinstance(row, sqlite3.Row) else row[0])


def _store_quality_metrics(
    connection: sqlite3.Connection,
    week_label: str,
    total_posts: int,
    strong_count: int,
    watch_count: int,
    cultural_count: int,
    noise_count: int,
    avg_signal_score: float | None,
    project_match_count: int,
    output_word_count: int,
) -> None:
    connection.execute(
        """
        INSERT OR REPLACE INTO quality_metrics (
            week_label,
            computed_at,
            total_posts,
            strong_count,
            watch_count,
            cultural_count,
            noise_count,
            avg_signal_score,
            project_match_count,
            output_word_count
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            week_label,
            _utc_now_iso(),
            total_posts,
            strong_count,
            watch_count,
            cultural_count,
            noise_count,
            avg_signal_score,
            project_match_count,
            output_word_count,
        ),
    )


def _render_empty_digest(week_label: str, date_range: str) -> str:
    return (
        f"## Weekly Briefing — {week_label}\n"
        f"*{date_range}*\n\n"
        "No posts were available for the last 7 days.\n"
    )


def _build_editorial_brief_message(
    *,
    week_label: str,
    posts: list[dict],
    bucket_counts: dict,
    top_topics: list[dict],
    model: str | None,
) -> str:
    fallback = build_brief_message(
        week_label=week_label,
        posts=posts,
        bucket_counts=bucket_counts,
        top_topics=top_topics,
    )
    if not posts:
        return fallback

    ranked_posts = sorted(
        posts,
        key=lambda post: (
            -float(post.get("signal_score") or 0.0),
            -int(post.get("view_count") or 0),
        ),
    )[:8]
    compact_posts = [
        {
            "channel": post.get("channel_username"),
            "url": post.get("message_url"),
            "topic": post.get("topic_label"),
            "score": post.get("signal_score"),
            "text": _make_editorial_excerpt(post.get("content"), limit=900),
        }
        for post in ranked_posts
    ]
    system = (
        "Ты редактор короткого Telegram weekly-поста для основателя, который строит AI-инструменты. "
        "Пиши как человек: ясный тезис недели, 2-3 сюжета, почему это важно, что делать дальше. "
        "Не копируй длинные фрагменты постов. Не используй служебные слова bucket, strong, watch, label, score. "
        "Не обрывай предложения многоточиями. Не пиши markdown-таблицы. Русский язык."
    )
    prompt = "\n".join(
        [
            f"Неделя: {week_label}",
            f"Счетчики: {json.dumps(bucket_counts, ensure_ascii=False, sort_keys=True)}",
            f"Темы: {json.dumps(top_topics, ensure_ascii=False)}",
            "Посты:",
            json.dumps(compact_posts, ensure_ascii=False, indent=2),
            "",
            "Верни только готовый Telegram-текст в таком формате:",
            "Бриф недели: [человеческий заголовок-тезис]",
            "",
            "[2-3 предложения: что за неделя и главный вывод]",
            "",
            "1. [Сюжет]",
            "[2-3 предложения: что произошло и почему это важно для нас]",
            "Источник: [channel] | [url]",
            "",
            "2. ...",
            "",
            "Что делать дальше: [одна конкретная строка]",
            "",
            "Ограничение: 1800 символов. Никаких обрезанных предложений.",
        ]
    )
    try:
        message = complete(prompt=prompt, system=system, category="digest", model=model).strip()
    except Exception:
        LOGGER.warning("Editorial weekly brief synthesis failed; using deterministic fallback", exc_info=True)
        return fallback
    if not _editorial_brief_is_usable(message):
        LOGGER.warning("Editorial weekly brief synthesis failed validation; using deterministic fallback")
        return fallback
    return message[:2200].strip()


def _make_editorial_excerpt(value: str | None, *, limit: int) -> str:
    compact = " ".join((value or "").split())
    if len(compact) <= limit:
        return compact
    trimmed = compact[:limit].rstrip()
    split_at = trimmed.rfind(". ")
    if split_at >= 160:
        return trimmed[: split_at + 1]
    split_at = trimmed.rfind(" ")
    if split_at >= 160:
        return trimmed[:split_at].rstrip()
    return trimmed


def _editorial_brief_is_usable(message: str) -> bool:
    text = message.strip()
    if len(text) < 200:
        return False
    forbidden = ("bucket", "strong", "watch", "label", "score")
    lowered = text.lower()
    if any(token in lowered for token in forbidden):
        return False
    if "…" in text or "..." in text:
        return False
    return "Источник:" in text


def run_digest(settings: Settings, force_delivery: bool = False) -> DigestResult:
    week_label = _compute_week_label()
    date_range = _format_date_range(week_label)
    cutoff_iso = (_utc_now() - timedelta(days=7)).isoformat().replace("+00:00", "Z")

    # Step 1: Run scoring engine before fetching for synthesis
    try:
        scoring_summary = score_posts(settings, since_days=7)
        LOGGER.info(
            "Scoring complete strong=%d watch=%d cultural=%d noise=%d avg=%.4f",
            scoring_summary.get("strong", 0),
            scoring_summary.get("watch", 0),
            scoring_summary.get("cultural", 0),
            scoring_summary.get("noise", 0),
            scoring_summary.get("avg_signal_score", 0.0),
        )
    except Exception:
        LOGGER.warning("score_posts failed; proceeding without scoring (bucket=None fallback)", exc_info=True)

    with sqlite3.connect(settings.db_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        connection.execute("PRAGMA journal_mode = WAL;")

        buckets = _fetch_scored_posts(connection, cutoff_iso)
        post_count = buckets["all_post_count"]
        channel_count = buckets["channel_count"]
        topic_counts = buckets["topic_counts"]

        if post_count == 0:
            LOGGER.warning("Digest generation found no posts since cutoff=%s", cutoff_iso)
            empty_digest = _render_empty_digest(week_label, date_range)
            empty_digest = _append_github_section(empty_digest, settings)
            empty_word_count = _count_words(empty_digest)
            output_path = _write_digest_file(week_label, empty_digest)
            html_path = None
            try:
                html_path = write_report_html(week_label, empty_digest)
            except OSError:
                LOGGER.warning("Failed to write HTML review week=%s", week_label, exc_info=True)
            connection.execute("BEGIN")
            digest_id = _store_digest(connection, week_label, empty_digest, "", None, 0)
            _store_quality_metrics(
                connection,
                week_label=week_label,
                total_posts=0,
                strong_count=0,
                watch_count=0,
                cultural_count=0,
                noise_count=0,
                avg_signal_score=None,
                project_match_count=0,
                output_word_count=empty_word_count,
            )
            connection.commit()
            receipt_audit_note = None
            evidence_summary = None
            evidence_summary_note = None
            try:
                receipt = _create_research_brief_receipt(
                    connection,
                    week_label=week_label,
                    generated_at=_utc_now_iso(),
                    window_start=cutoff_iso,
                    window_end=_utc_now_iso(),
                    buckets=buckets,
                    digest_id=digest_id,
                    markdown_path=output_path,
                    json_path=None,
                    html_path=html_path,
                    llm_provider=None,
                    llm_model=None,
                    llm_category=None,
                )
                evidence_summary = summarize_research_brief_evidence(connection, receipt)
                evidence_summary_note = _format_receipt_evidence_notification(evidence_summary)
                empty_digest = _upsert_evidence_summary_section(empty_digest, evidence_summary)
                empty_word_count = _count_words(empty_digest)
                output_path = _write_digest_file(week_label, empty_digest)
                try:
                    html_path = write_report_html(week_label, empty_digest)
                except OSError:
                    LOGGER.warning("Failed to rewrite HTML review week=%s", week_label, exc_info=True)
                connection.execute(
                    "UPDATE digests SET content_md = ? WHERE id = ?",
                    (empty_digest, digest_id),
                )
                connection.execute(
                    "UPDATE quality_metrics SET output_word_count = ? WHERE week_label = ?",
                    (empty_word_count, week_label),
                )
                connection.commit()
                receipt_audit_note = _build_receipt_audit_note(receipt)
            except Exception:
                LOGGER.warning("Failed to create research brief receipt week=%s", week_label, exc_info=True)
            health_alert = _build_digest_health_alert(
                week_label,
                post_count=0,
                strong_count=0,
                watch_count=0,
            )
            report_quality_findings = _validate_weekly_report_quality(
                week_label=week_label,
                content_md=empty_digest,
                post_count=0,
                strong_count=0,
                watch_count=0,
                cultural_count=0,
                noise_count=0,
                project_match_count=0,
                output_word_count=empty_word_count,
            )
            report_quality_warning = format_findings_for_notification(report_quality_findings)
            operator_message = build_brief_message(
                week_label=week_label,
                posts=[],
                bucket_counts=buckets.get("bucket_counts", {}),
                top_topics=[],
            )
            write_weekly_message(week_label, "brief", operator_message)
            try:
                _send_weekly_review_to_telegram_owner(
                    connection=connection,
                    content_md=empty_digest,
                    week_label=week_label,
                    strong_count=0,
                    watch_count=0,
                    html_path=html_path,
                    digest_id=digest_id,
                    post_count=0,
                    noise_count=0,
                    force_delivery=force_delivery,
                    health_alert=health_alert,
                    receipt_audit_note=receipt_audit_note,
                    evidence_summary_note=evidence_summary_note,
                    evidence_summary=evidence_summary,
                    report_quality_warning=report_quality_warning,
                    operator_message=operator_message,
                )
            except Exception:
                LOGGER.warning("Failed to send digest to Telegram owner week=%s", week_label, exc_info=True)
            return DigestResult(week_label=week_label, output_path=str(output_path), post_count=0, json_path="")

        # Step 2: Build inputs for prompt
        top_topics = [
            {"label": label, "post_count": count}
            for label, count in sorted(topic_counts.items(), key=lambda item: (-item[1], item[0]))[:5]
        ]

        scored_posts_flat = _build_scored_posts_for_prompt(buckets)
        noise_count = len(buckets["noise"])
        noise_summary = _build_noise_summary(buckets["noise"], topic_counts)

        # Step 3: Build and run LLM synthesis
        system_prompt, user_template = _load_prompt_sections()
        prompt = (
            user_template
            .replace("{week_label}", week_label)
            .replace("{date_range}", date_range)
            .replace("{total_post_count}", str(post_count))
            .replace("{channel_count}", str(channel_count))
            .replace("{noise_count}", str(noise_count))
            .replace("{scored_posts}", json.dumps(scored_posts_flat, ensure_ascii=False))
            .replace("{topic_summary}", json.dumps(top_topics, ensure_ascii=False))
            .replace("{noise_summary}", noise_summary)
        )

        digest_model = route("synthesis")
        llm_brief = complete(
            prompt=prompt,
            system=system_prompt,
            category="digest",
            model=digest_model,
        )

        full_buckets = buckets.get("full_buckets", {})
        signal_posts = [
            *full_buckets.get("strong", buckets["strong"]),
            *full_buckets.get("watch", buckets["watch"]),
            *full_buckets.get("cultural", buckets["cultural"]),
            *full_buckets.get("noise", buckets["noise"]),
        ]
        try:
            signal_report = format_signal_report(signal_posts, settings, reader_mode=True)
            content_md = signal_report
        except Exception:
            LOGGER.warning("Signal-first section generation failed; continuing without it", exc_info=True)
            content_md = llm_brief

        # Step 4: Validate output length
        llm_word_count = _count_words(content_md)
        if llm_word_count > MAX_OUTPUT_WORDS:
            LOGGER.warning(
                "Digest output exceeds word limit week=%s words=%d limit=%d",
                week_label, llm_word_count, MAX_OUTPUT_WORDS,
            )

        content_md = _append_github_section(content_md, settings)
        output_word_count = _count_words(content_md)
        operator_message = _build_editorial_brief_message(
            week_label=week_label,
            posts=signal_posts,
            bucket_counts=buckets.get("bucket_counts", {}),
            top_topics=top_topics,
            model=digest_model,
        )
        write_weekly_message(week_label, "brief", operator_message)

        # Step 5: Persist
        generated_at = _utc_now_iso()
        report = _build_research_report(
            week_label=week_label,
            date_range=date_range,
            generated_at=generated_at,
            post_count=post_count,
            channel_count=channel_count,
            content_md=content_md,
            top_topics=top_topics,
            scored_posts_flat=scored_posts_flat,
        )
        content_json = json.dumps(asdict(report), ensure_ascii=False)
        json_path = _write_digest_json_file(week_label, report)
        output_path = _write_digest_file(week_label, content_md)
        html_path = None
        try:
            html_path = write_report_html(week_label, content_md)
        except OSError:
            LOGGER.warning("Failed to write HTML review week=%s", week_label, exc_info=True)

        connection.execute("BEGIN")
        digest_id = _store_digest(connection, week_label, content_md, content_json, None, post_count)
        _store_quality_metrics(
            connection,
            week_label=week_label,
            total_posts=post_count,
            strong_count=buckets["bucket_counts"]["strong"],
            watch_count=buckets["bucket_counts"]["watch"],
            cultural_count=buckets["bucket_counts"]["cultural"],
            noise_count=buckets["bucket_counts"]["noise"],
            avg_signal_score=buckets["avg_signal_score"],
            project_match_count=buckets["project_match_count"],
            output_word_count=output_word_count,
        )
        connection.commit()
        receipt_audit_note = None
        evidence_summary = None
        evidence_summary_note = None
        try:
            receipt = _create_research_brief_receipt(
                connection,
                week_label=week_label,
                generated_at=generated_at,
                window_start=cutoff_iso,
                window_end=generated_at,
                buckets=buckets,
                digest_id=digest_id,
                markdown_path=output_path,
                json_path=json_path,
                html_path=html_path,
                llm_provider=settings.model_provider,
                llm_model=digest_model,
                llm_category="digest",
            )
            LOGGER.info(
                "Research brief receipt created week=%s receipt_id=%s digest_id=%d",
                week_label,
                receipt.get("receipt_id", ""),
                digest_id,
            )
            evidence_summary = summarize_research_brief_evidence(connection, receipt)
            evidence_summary_note = _format_receipt_evidence_notification(evidence_summary)
            content_md = _upsert_evidence_summary_section(content_md, evidence_summary)
            output_word_count = _count_words(content_md)
            report = _build_research_report(
                week_label=week_label,
                date_range=date_range,
                generated_at=generated_at,
                post_count=post_count,
                channel_count=channel_count,
                content_md=content_md,
                top_topics=top_topics,
                scored_posts_flat=scored_posts_flat,
            )
            content_json = json.dumps(asdict(report), ensure_ascii=False)
            json_path = _write_digest_json_file(week_label, report)
            output_path = _write_digest_file(week_label, content_md)
            try:
                html_path = write_report_html(week_label, content_md)
            except OSError:
                LOGGER.warning("Failed to rewrite HTML review week=%s", week_label, exc_info=True)
            connection.execute(
                "UPDATE digests SET content_md = ?, content_json = ? WHERE id = ?",
                (content_md, content_json, digest_id),
            )
            connection.execute(
                "UPDATE quality_metrics SET output_word_count = ? WHERE week_label = ?",
                (output_word_count, week_label),
            )
            connection.commit()
            receipt_audit_note = _build_receipt_audit_note(receipt)
        except Exception:
            LOGGER.warning("Failed to create research brief receipt week=%s", week_label, exc_info=True)

        LOGGER.info(
            "Digest generation complete week=%s posts=%d strong=%d watch=%d words=%d output=%s",
            week_label, post_count,
            len(buckets["strong"]), len(buckets["watch"]),
            output_word_count, output_path,
        )

        health_alert = _build_digest_health_alert(
            week_label,
            post_count=post_count,
            strong_count=buckets["bucket_counts"]["strong"],
            watch_count=buckets["bucket_counts"]["watch"],
            channel_count=channel_count,
            topic_count=len(topic_counts),
        )
        if health_alert:
            LOGGER.warning("Digest health alert week=%s alert=%s", week_label, health_alert.replace("\n", " | "))

        report_quality_findings = _validate_weekly_report_quality(
            week_label=week_label,
            content_md=content_md,
            post_count=post_count,
            strong_count=buckets["bucket_counts"]["strong"],
            watch_count=buckets["bucket_counts"]["watch"],
            cultural_count=buckets["bucket_counts"]["cultural"],
            noise_count=buckets["bucket_counts"]["noise"],
            project_match_count=buckets["project_match_count"],
            output_word_count=output_word_count,
        )
        report_quality_warning = format_findings_for_notification(report_quality_findings)

        try:
            _send_weekly_review_to_telegram_owner(
                connection=connection,
                content_md=content_md,
                week_label=week_label,
                strong_count=buckets["bucket_counts"]["strong"],
                watch_count=buckets["bucket_counts"]["watch"],
                html_path=html_path,
                digest_id=digest_id,
                post_count=post_count,
                noise_count=buckets["bucket_counts"]["noise"],
                force_delivery=force_delivery,
                health_alert=health_alert,
                receipt_audit_note=receipt_audit_note,
                evidence_summary_note=evidence_summary_note,
                evidence_summary=evidence_summary,
                report_quality_warning=report_quality_warning,
                operator_message=operator_message,
            )
        except Exception:
            LOGGER.warning("Failed to send digest to Telegram owner week=%s", week_label, exc_info=True)

        try:
            recommendation_summary = recommendations_module.run_recommendations(settings, force_delivery=force_delivery)
            insights_text = str(recommendation_summary.get("text") or "").strip()
            has_standalone_delivery = bool(recommendation_summary.get("html_path") or recommendation_summary.get("telegraph_url"))
            token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
            chat_id = os.environ.get("TELEGRAM_OWNER_CHAT_ID", "").strip()
            if insights_text and not has_standalone_delivery and token and chat_id:
                time.sleep(1)
                send_text(chat_id=chat_id, text=insights_text, token=token, parse_mode=None)
        except Exception:
            LOGGER.warning("Insights generation failed, skipping", exc_info=True)

    return DigestResult(
        week_label=week_label,
        output_path=str(output_path),
        post_count=post_count,
        json_path=str(json_path),
    )
