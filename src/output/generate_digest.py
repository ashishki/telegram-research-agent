import json
import logging
import re
import sqlite3
from datetime import timezone, date, datetime, timedelta
from pathlib import Path

from config.settings import PROJECT_ROOT, Settings
from llm.client import complete


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


def _extract_markdown_section(text: str, heading: str) -> str:
    pattern = re.compile(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)
    match = pattern.search(text)
    if not match:
        raise ValueError(f"Section not found in prompt file: {heading}")
    return match.group(1).strip()


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


def _store_digest(connection: sqlite3.Connection, week_label: str, content_md: str, post_count: int) -> None:
    connection.execute(
        """
        INSERT OR REPLACE INTO digests (week_label, generated_at, content_md, post_count)
        VALUES (?, ?, ?, ?)
        """,
        (week_label, _utc_now_iso(), content_md, post_count),
    )


def _render_empty_digest(week_label: str, date_range: str) -> str:
    return (
        f"## Weekly Digest — {week_label}\n"
        f"*{date_range}*\n\n"
        "No posts were available for the last 7 days.\n"
    )


def run_digest(settings: Settings) -> dict:
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
            output_path = _write_digest_file(week_label, empty_digest)
            connection.execute("BEGIN")
            _store_digest(connection, week_label, empty_digest, 0)
            connection.commit()
            return {
                "week_label": week_label,
                "output_path": str(output_path),
                "post_count": 0,
            }

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

        content_md = complete(prompt=prompt, system=system_prompt)
        if not content_md.lstrip().startswith(f"## Weekly Digest — {week_label}"):
            LOGGER.warning("Digest response did not match expected heading for week=%s", week_label)

        output_path = _write_digest_file(week_label, content_md)
        connection.execute("BEGIN")
        _store_digest(connection, week_label, content_md, post_count)
        connection.commit()

    LOGGER.info("Digest generation complete week=%s posts=%d output=%s", week_label, post_count, output_path)
    return {
        "week_label": week_label,
        "output_path": str(output_path),
        "post_count": post_count,
    }
