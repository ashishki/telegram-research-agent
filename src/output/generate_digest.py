import json
import logging
import os
import sqlite3
from dataclasses import asdict
from datetime import timezone, date, datetime, timedelta
from pathlib import Path

from config.settings import PROJECT_ROOT, Settings
from llm.client import complete
from output.report_schema import (
    DigestResult,
    EvidenceItem,
    KeyFinding,
    ReportMeta,
    ReportSection,
    ResearchReport,
)
from output.report_utils import _extract_markdown_section
from reporting.renderer import render_pdf

try:
    from bot.telegram_delivery import send_text
except ImportError:  # pragma: no cover - direct module execution fallback
    from src.bot.telegram_delivery import send_text

try:
    from integrations.github_crossref import NO_OVERLAP_NOTE, crossref_repos_to_topics
    from integrations.github_sync import sync_github_projects
except Exception:  # pragma: no cover - graceful import fallback
    NO_OVERLAP_NOTE = "active this week, no Telegram overlap found"
    crossref_repos_to_topics = None
    sync_github_projects = None


LOGGER = logging.getLogger(__name__)
PROMPT_PATH = PROJECT_ROOT / "docs" / "prompts" / "digest_generation.md"
OUTPUT_DIR = PROJECT_ROOT / "data" / "output" / "digests"
TEXT_EXCERPT_LENGTH = 200


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


def _append_github_section(content_md: str, settings: Settings) -> str:
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
    for repo in repos:
        repo_name = repo["name"]
        github_repo = repo.get("github_repo") or repo_name
        commits_label = (
            f"{int(repo.get('weekly_commits') or 0)} commits this week"
            if int(repo.get("weekly_commits") or 0) > 0
            else "no activity"
        )
        matched_topics = topic_matches.get(repo_name, [])
        if not matched_topics:
            match_label = "no Telegram topic matches"
        elif matched_topics == [NO_OVERLAP_NOTE]:
            match_label = NO_OVERLAP_NOTE
        else:
            match_label = ", ".join(matched_topics)
        lines.append(f"- [{repo_name}](https://github.com/{github_repo}) — {commits_label} — {match_label}")

    return content_md.rstrip() + "\n\n" + "\n".join(lines).strip() + "\n"


def _extract_markdown_subsection(text: str, heading: str) -> str:
    import re

    pattern = re.compile(rf"^### {re.escape(heading)}\n(.*?)(?=^### |\Z)", re.MULTILINE | re.DOTALL)
    match = pattern.search(text)
    if not match:
        return ""
    return match.group(1).strip()


def _extract_executive_summary(content_md: str) -> list[str]:
    overview = _extract_markdown_subsection(content_md, "Overview")
    if not overview:
        return []
    normalized = " ".join(overview.split())
    parts = [part.strip() for part in normalized.split(". ") if part.strip()]
    sentences: list[str] = []
    for part in parts:
        sentence = part if part.endswith(".") else f"{part}."
        sentences.append(sentence)
    return sentences


def _extract_sections(content_md: str, headings: list[str]) -> list[ReportSection]:
    return [
        ReportSection(heading=heading, body=_extract_markdown_subsection(content_md, heading))
        for heading in headings
    ]


def _build_research_report(
    week_label: str,
    date_range: str,
    generated_at: str,
    post_count: int,
    channel_count: int,
    content_md: str,
    top_topics: list[dict[str, object]],
    notable_posts: list[dict[str, object]],
) -> ResearchReport:
    section_headings = [
        "Overview",
        "Top Topics",
        "Signal Posts",
        "Noise Patterns",
        "One Thing to Act On",
    ]
    evidence_by_topic: dict[str, list[str]] = {}
    for index, post in enumerate(notable_posts, start=1):
        topic_label = str(post.get("topic_label") or "Unlabeled")
        evidence_by_topic.setdefault(topic_label, []).append(f"S{index}")
    return ResearchReport(
        meta=ReportMeta(
            week_label=week_label,
            date_range=date_range,
            generated_at=generated_at,
            post_count=post_count,
            channel_count=channel_count,
        ),
        executive_summary=_extract_executive_summary(content_md),
        key_findings=[
            KeyFinding(
                title=str(topic["label"]),
                body=f"{int(topic['post_count'])} posts captured this week.",
                evidence_ids=evidence_by_topic.get(str(topic["label"]), []),
            )
            for topic in top_topics
        ],
        sections=_extract_sections(content_md, section_headings),
        evidence=[
            EvidenceItem(
                id=f"S{index}",
                channel=str(post["channel_username"]),
                date=str(post["posted_at"]),
                excerpt=str(post["text_excerpt"]),
                url=str(post["message_url"] or ""),
            )
            for index, post in enumerate(notable_posts, start=1)
        ],
        project_relevance=[],
        confidence_notes=(
            "This report reflects the last 7 days of ingested Telegram posts. "
            "Coverage is strongest for the highest-volume topics and most-viewed evidence."
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
        INSERT OR REPLACE INTO digests (week_label, generated_at, content_md, content_json, pdf_path, post_count)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (week_label, _utc_now_iso(), content_md, content_json, pdf_path, post_count),
    )


def _render_empty_digest(week_label: str, date_range: str) -> str:
    return (
        f"## Weekly Digest — {week_label}\n"
        f"*{date_range}*\n\n"
        "No posts were available for the last 7 days.\n"
    )


def run_digest(settings: Settings) -> DigestResult:
    week_label = _compute_week_label()
    date_range = _format_date_range(week_label)
    cutoff_iso = (_utc_now() - timedelta(days=7)).isoformat().replace("+00:00", "Z")

    with sqlite3.connect(settings.db_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        connection.execute("PRAGMA journal_mode = WAL;")

        posts = connection.execute(
            """
            SELECT
                posts.id,
                posts.channel_username,
                posts.content,
                posts.posted_at,
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

        unique_posts: dict[int, sqlite3.Row] = {}
        topic_counts: dict[str, int] = {}
        topic_by_post: dict[int, str] = {}

        for row in posts:
            post_id = row["id"]
            if post_id not in unique_posts:
                unique_posts[post_id] = row
            topic_label = row["topic_label"] or "Unlabeled"
            if post_id not in topic_by_post:
                topic_by_post[post_id] = topic_label
            topic_counts[topic_label] = topic_counts.get(topic_label, 0) + 1

        post_count = len(unique_posts)
        if post_count == 0:
            LOGGER.warning("Digest generation found no posts since cutoff=%s", cutoff_iso)
            empty_digest = _render_empty_digest(week_label, date_range)
            empty_digest = _append_github_section(empty_digest, settings)
            output_path = _write_digest_file(week_label, empty_digest)
            connection.execute("BEGIN")
            _store_digest(connection, week_label, empty_digest, "", None, 0)
            connection.commit()
            try:
                _send_digest_to_telegram_owner(content_md=empty_digest, week_label=week_label)
            except Exception:
                LOGGER.warning("Failed to send digest to Telegram owner week=%s", week_label, exc_info=True)
            return DigestResult(week_label=week_label, output_path=str(output_path), post_count=0, json_path="")

        top_topics = [
            {"label": label, "post_count": count}
            for label, count in sorted(topic_counts.items(), key=lambda item: (-item[1], item[0]))[:5]
        ]

        sorted_posts = sorted(
            unique_posts.values(),
            key=lambda row: (-int(row["view_count"] or 0), row["posted_at"], row["id"]),
        )
        notable_posts = [
            {
                "channel_username": row["channel_username"],
                "text_excerpt": _make_excerpt(row["content"]),
                "view_count": int(row["view_count"] or 0),
                "message_url": row["message_url"],
                "topic_label": topic_by_post.get(row["id"], "Unlabeled"),
            }
            for row in sorted_posts[:10]
        ]
        channel_count = len({row["channel_username"] for row in unique_posts.values()})

        system_prompt, user_template = _load_prompt_sections()
        prompt = (
            user_template.replace("{week_label}", week_label)
            .replace("{date_range}", date_range)
            .replace("{topic_summary}", json.dumps(top_topics, ensure_ascii=True))
            .replace("{notable_posts}", json.dumps(notable_posts, ensure_ascii=True))
            .replace("{total_post_count}", str(post_count))
            .replace("{channel_count}", str(channel_count))
        )

        content_md = complete(prompt=prompt, system=system_prompt, category="digest")
        if not content_md.lstrip().startswith(f"## Weekly Digest — {week_label}"):
            LOGGER.warning("Digest response did not match expected heading for week=%s", week_label)
        required_digest_sections = [
            "### Overview",
            "### Top Topics",
            "### Signal Posts",
            "### Noise Patterns",
            "### One Thing to Act On",
        ]
        for section_heading in required_digest_sections:
            if section_heading not in content_md:
                LOGGER.warning(
                    "Digest response missing required section %r for week=%s",
                    section_heading,
                    week_label,
                )
        content_md = _append_github_section(content_md, settings)

        generated_at = _utc_now_iso()
        report = _build_research_report(
            week_label=week_label,
            date_range=date_range,
            generated_at=generated_at,
            post_count=post_count,
            channel_count=channel_count,
            content_md=content_md,
            top_topics=top_topics,
            notable_posts=[
                {
                    "channel_username": row["channel_username"],
                    "posted_at": row["posted_at"],
                    "text_excerpt": _make_excerpt(row["content"]),
                    "message_url": row["message_url"],
                }
                for row in sorted_posts[:10]
            ],
        )
        content_json = json.dumps(asdict(report), ensure_ascii=False)
        json_path = _write_digest_json_file(week_label, report)
        output_path = _write_digest_file(week_label, content_md)
        pdf_output_path = OUTPUT_DIR / f"{week_label}.pdf"
        # T21: removed from delivery path
        # rendered_pdf_path = render_pdf(report, pdf_output_path)
        rendered_pdf_path = None
        connection.execute("BEGIN")
        _store_digest(
            connection,
            week_label,
            content_md,
            content_json,
            str(rendered_pdf_path) if rendered_pdf_path else None,
            post_count,
        )
        connection.commit()

    LOGGER.info("Digest generation complete week=%s posts=%d output=%s", week_label, post_count, output_path)
    try:
        _send_digest_to_telegram_owner(content_md=content_md, week_label=week_label)
    except Exception:
        LOGGER.warning("Failed to send digest to Telegram owner week=%s", week_label, exc_info=True)

    # Send insights as second message (1 message after digest)
    try:
        from output.generate_recommendations import run_recommendations
        insights_result = run_recommendations(settings)
        insights_text = insights_result.get("text", "") if isinstance(insights_result, dict) else str(insights_result)
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.environ.get("TELEGRAM_OWNER_CHAT_ID", "").strip()
        if insights_text and token and chat_id:
            send_text(token=token, chat_id=chat_id, text=insights_text)
    except Exception as e:
        LOGGER.warning("Insights generation failed, skipping: %s", e)

    return DigestResult(
        week_label=week_label,
        output_path=str(output_path),
        post_count=post_count,
        json_path=str(json_path),
    )
