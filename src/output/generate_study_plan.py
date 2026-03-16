"""Weekly 3-hour study plan generator."""
import json
import logging
import os
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from config.settings import PROJECT_ROOT, Settings
from llm.client import LLMClient


LOGGER = logging.getLogger(__name__)
PROMPT_PATH = PROJECT_ROOT / "docs" / "prompts" / "study_plan.md"
OUTPUT_DIR = PROJECT_ROOT / "data" / "output" / "study_plans"
BOOKS_API_URL = "https://api.github.com/repos/marangelologic/books/contents"
RELEVANT_BOOKS = {
    "Designing Data Intensive Applications": "data storage, distributed systems, AI infrastructure",
    "building-microservices-designing-fine-grained-systems- 2nd edition": "microservices, agent architecture",
    "Design Patterns Elements of Reusable Object-Oriented Software": "patterns for agent design",
    "Algorithms to Live By - Brian Christian": "algorithmic thinking, approachable",
    "Designing_APIs_with_Swagger_and_OpenAPI_(2022)": "API design for AI services",
    "dokumen.pub_code-complete-a-practical-handbook-of-software-construction-with-pdf-outline-2nd-edition": "software engineering fundamentals",
    "A Common-Sense Guide to Data Structures and Algorithms - Level Up Your Core Programming Skills": "data structures foundation",
    "The_Managers_Path_A_Guide_for_Tech_Leade": "engineering growth path",
}
TELEGRAM_MESSAGE_CHUNK_SIZE = 4000


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat().replace("+00:00", "Z")


def _compute_week_label() -> str:
    year, week, _ = _utc_now().isocalendar()
    return f"{year}-W{week:02d}"


def _extract_markdown_section(text: str, heading: str) -> str:
    import re

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


def _fallback_books_catalog() -> list[dict[str, str]]:
    fallback: list[dict[str, str]] = []
    for name, relevance in RELEVANT_BOOKS.items():
        encoded_name = urllib.parse.quote(name, safe="")
        fallback.append(
            {
                "name": name,
                "url": f"https://raw.githubusercontent.com/marangelologic/books/master/{encoded_name}",
                "relevance": relevance,
            }
        )
    return fallback


def _fetch_books_catalog() -> list[dict[str, str]]:
    request_obj = urllib.request.Request(
        BOOKS_API_URL,
        headers={"User-Agent": "telegram-research-agent"},
    )
    try:
        with urllib.request.urlopen(request_obj, timeout=15) as response:
            payload = response.read().decode("utf-8")
        items = json.loads(payload)
        catalog: list[dict[str, str]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            raw_name = str(item.get("name", "")).strip()
            stem = Path(raw_name).stem
            if stem not in RELEVANT_BOOKS:
                continue
            download_url = str(item.get("download_url", "")).strip()
            if not download_url:
                continue
            catalog.append(
                {
                    "name": stem,
                    "url": download_url,
                    "relevance": RELEVANT_BOOKS[stem],
                }
            )
        if catalog:
            return catalog
        LOGGER.warning("Books catalog fetch returned no relevant matches; using fallback list")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        LOGGER.warning("Failed to fetch books catalog; using fallback list", exc_info=True)
    except Exception:
        LOGGER.warning("Unexpected error while fetching books catalog; using fallback list", exc_info=True)
    return _fallback_books_catalog()


def _week_bounds(week_label: str) -> tuple[str, str]:
    year_str, week_str = week_label.split("-W", maxsplit=1)
    week_start = date.fromisocalendar(int(year_str), int(week_str), 1)
    start = datetime.combine(week_start, datetime.min.time(), tzinfo=timezone.utc)
    end = start + timedelta(days=7)
    return (
        start.isoformat().replace("+00:00", "Z"),
        end.isoformat().replace("+00:00", "Z"),
    )


def _fetch_top_posts(connection: sqlite3.Connection, week_label: str, limit: int = 8) -> list[str]:
    week_start_iso, week_end_iso = _week_bounds(week_label)
    rows = connection.execute(
        """
        SELECT posts.channel_username, posts.posted_at, posts.content
        FROM posts
        INNER JOIN raw_posts ON raw_posts.id = posts.raw_post_id
        WHERE posts.posted_at >= ? AND posts.posted_at < ?
        ORDER BY COALESCE(raw_posts.view_count, 0) DESC, posts.posted_at DESC
        LIMIT ?
        """,
        (week_start_iso, week_end_iso, limit),
    ).fetchall()
    results: list[str] = []
    for row in rows:
        content = " ".join((row["content"] or "").split())
        results.append(f"{row['channel_username']} | {row['posted_at'][:10]}: {content[:200]}")
    return results


def _fetch_topics_this_week(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT t.label, t.description, t.post_count
        FROM topics t
        ORDER BY t.post_count DESC
        LIMIT 10
        """
    ).fetchall()
    return [
        {
            "label": row["label"],
            "description": row["description"],
            "post_count": row["post_count"],
        }
        for row in rows
    ]


def _fetch_previous_plan_topics(connection: sqlite3.Connection) -> list[str]:
    row = connection.execute(
        """
        SELECT topics_covered
        FROM study_plans
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    if row is None or not row["topics_covered"]:
        return []
    try:
        parsed = json.loads(row["topics_covered"])
    except json.JSONDecodeError:
        LOGGER.warning("Failed to parse previous study plan topics", exc_info=True)
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if str(item).strip()]


def _fetch_active_projects(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(
        """
        SELECT name, keywords
        FROM projects
        WHERE active = 1 AND last_commit_at IS NOT NULL
        ORDER BY last_commit_at DESC
        LIMIT 8
        """
    ).fetchall()
    return [f"{row['name']}: {row['keywords'] or ''}".rstrip() for row in rows]


def _write_study_plan_file(week_label: str, content_md: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{week_label}.md"
    output_path.write_text(content_md, encoding="utf-8")
    return output_path


def _chunk_text(text: str, chunk_size: int = TELEGRAM_MESSAGE_CHUNK_SIZE) -> list[str]:
    if not text:
        return [""]

    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= chunk_size:
            chunks.append(remaining)
            break

        split_at = remaining.rfind("\n", 0, chunk_size)
        if split_at <= 0:
            split_at = remaining.rfind(" ", 0, chunk_size)
        if split_at <= 0:
            split_at = chunk_size

        chunk = remaining[:split_at].rstrip()
        if not chunk:
            chunk = remaining[:chunk_size]
            split_at = len(chunk)
        chunks.append(chunk)
        remaining = remaining[split_at:].lstrip()

    return chunks


def generate_study_plan(settings: Settings) -> str:
    week_label = _compute_week_label()
    output_path = OUTPUT_DIR / f"{week_label}.md"

    with sqlite3.connect(settings.db_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        connection.execute("PRAGMA journal_mode = WAL;")

        existing_row = connection.execute(
            """
            SELECT content_md
            FROM study_plans
            WHERE week_label = ?
            """,
            (week_label,),
        ).fetchone()
        if existing_row is not None:
            content_md = str(existing_row["content_md"])
            if not output_path.exists():
                _write_study_plan_file(week_label, content_md)
            return content_md

        system_prompt, user_template = _load_prompt_sections()
        topics = _fetch_topics_this_week(connection)
        top_posts = _fetch_top_posts(connection, week_label)
        books_catalog = _fetch_books_catalog()
        projects = _fetch_active_projects(connection)
        previous_topics = _fetch_previous_plan_topics(connection)

        post_count = sum(int(topic.get("post_count") or 0) for topic in topics)
        prompt = (
            user_template.replace("{week_label}", week_label)
            .replace("{post_count}", str(post_count))
            .replace("{topics_json}", json.dumps(topics, ensure_ascii=True, indent=2))
            .replace("{top_posts}", json.dumps(top_posts, ensure_ascii=True, indent=2))
            .replace("{books_catalog}", json.dumps(books_catalog, ensure_ascii=True, indent=2))
            .replace("{projects_list}", json.dumps(projects, ensure_ascii=True, indent=2))
            .replace("{previous_topics}", json.dumps(previous_topics, ensure_ascii=True))
        )

        content_md = LLMClient.complete(
            prompt=prompt,
            system=system_prompt,
            max_tokens=3000,
            category="study_plan",
        )
        topics_covered = json.dumps([topic["label"] for topic in topics], ensure_ascii=True)

        connection.execute("BEGIN")
        connection.execute(
            """
            INSERT OR REPLACE INTO study_plans (week_label, generated_at, content_md, topics_covered)
            VALUES (?, ?, ?, ?)
            """,
            (week_label, _utc_now_iso(), content_md, topics_covered),
        )
        connection.commit()

    output_path = _write_study_plan_file(week_label, content_md)
    LOGGER.info("Study plan generation complete week=%s output=%s", week_label, output_path)
    return content_md


def send_study_reminder(settings: Settings, is_friday: bool = False) -> None:
    try:
        week_label = _compute_week_label()
        with sqlite3.connect(settings.db_path) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON;")
            connection.execute("PRAGMA journal_mode = WAL;")
            row = connection.execute(
                """
                SELECT content_md
                FROM study_plans
                WHERE week_label = ?
                """,
                (week_label,),
            ).fetchone()

        content_md = str(row["content_md"]) if row is not None else generate_study_plan(settings)
        prefix = (
            "📅 Пятница — успел поучиться? Вот план на эту неделю если нет:\n\n"
            if is_friday
            else "📅 Вторник — время учиться! Вот твой план на эту неделю:\n\n"
        )
        message = prefix + content_md

        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.environ.get("TELEGRAM_OWNER_CHAT_ID", "").strip()
        if not bot_token or not chat_id:
            LOGGER.warning("Study reminder skipped because Telegram bot credentials are not configured")
            return

        for chunk in _chunk_text(message):
            payload = urllib.parse.urlencode(
                {
                    "chat_id": chat_id,
                    "text": chunk,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": "true",
                }
            ).encode("utf-8")
            request_obj = urllib.request.Request(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                method="POST",
            )
            with urllib.request.urlopen(request_obj, timeout=60) as response:
                response.read()
        LOGGER.info("Study reminder sent week=%s is_friday=%s", week_label, is_friday)
    except Exception:
        LOGGER.warning("Failed to send study reminder", exc_info=True)
