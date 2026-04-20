import json
import logging
import os
import sqlite3
import time
from dataclasses import asdict
from datetime import timezone, date, datetime, timedelta
from pathlib import Path

from config.settings import PROJECT_ROOT, Settings
from llm.client import complete
from llm.router import route
from output import generate_recommendations as recommendations_module
from output.render_report import write_report_html
from output.signal_report import format_signal_report
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
    from bot.telegram_delivery import send_document, send_text
except ImportError:  # pragma: no cover
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
TEXT_EXCERPT_LENGTH = 250
MAX_STRONG = 3
MAX_WATCH = 3
MAX_CULTURAL = 1
MAX_OUTPUT_WORDS = 600


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


def _build_review_notification(week_label: str, strong_count: int, watch_count: int) -> str:
    return (
        f"Research Brief {week_label} is ready.\n"
        f"{strong_count} strong signals, {watch_count} watch.\n"
        "Open the full brief:"
    )[:300]


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


def _send_weekly_review_to_telegram_owner(
    connection: sqlite3.Connection,
    content_md: str,
    week_label: str,
    strong_count: int,
    watch_count: int,
    html_path: Path | None,
    force_delivery: bool = False,
) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_OWNER_CHAT_ID", "").strip()
    if not token or not chat_id:
        return

    delivery_state = _load_delivery_state(connection, week_label)
    if delivery_state["telegram_sent_at"] and not force_delivery:
        LOGGER.info("Weekly review delivery skipped week=%s because it was already sent", week_label)
        return

    notification = _build_review_notification(week_label, strong_count, watch_count)

    # Try Telegraph first
    if html_path is not None:
        try:
            html_content = html_path.read_text(encoding="utf-8")
            url = publish_article(title=f"Research Brief {week_label}", html_content=html_content)
            send_text(chat_id=chat_id, text=f"{notification}\n{url}", token=token, parse_mode=None)
            _mark_delivery_state(connection, week_label, telegraph_url=url, telegram_sent_at=_utc_now_iso())
            connection.commit()
            LOGGER.info("Weekly review published to Telegraph week=%s url=%s", week_label, url)
            return
        except Exception:
            LOGGER.warning(
                "Failed to publish Telegraph article week=%s; falling back to HTML attachment",
                week_label,
                exc_info=True,
            )

    send_text(chat_id=chat_id, text=notification, token=token, parse_mode=None)
    _mark_delivery_state(connection, week_label, telegram_sent_at=_utc_now_iso())
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
) -> None:
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
            _store_digest(connection, week_label, empty_digest, "", None, 0)
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
            try:
                _send_weekly_review_to_telegram_owner(
                    connection=connection,
                    content_md=empty_digest,
                    week_label=week_label,
                    strong_count=0,
                    watch_count=0,
                    html_path=html_path,
                    force_delivery=force_delivery,
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

        llm_brief = complete(
            prompt=prompt,
            system=system_prompt,
            category="digest",
            model=route("synthesis"),
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
        _store_digest(connection, week_label, content_md, content_json, None, post_count)
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

        LOGGER.info(
            "Digest generation complete week=%s posts=%d strong=%d watch=%d words=%d output=%s",
            week_label, post_count,
            len(buckets["strong"]), len(buckets["watch"]),
            output_word_count, output_path,
        )

        try:
            _send_weekly_review_to_telegram_owner(
                connection=connection,
                content_md=content_md,
                week_label=week_label,
                strong_count=buckets["bucket_counts"]["strong"],
                watch_count=buckets["bucket_counts"]["watch"],
                html_path=html_path,
                force_delivery=force_delivery,
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
