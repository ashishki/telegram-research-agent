"""Weekly study plan generator with completion tracking and reminders."""
import json
import logging
import os
import re
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from config.settings import PROJECT_ROOT, Settings
from db.retrieval import fetch_decisions
from llm.client import LLMClient
from output.context_memory import load_project_context, refresh_all_project_context_snapshots
from output.report_utils import _extract_markdown_section

try:
    from bot.telegram_delivery import send_text
    from delivery.telegraph import publish_article
    from output.render_report import render_report_html
except ImportError:  # pragma: no cover - direct module execution fallback
    from src.bot.telegram_delivery import send_text
    from src.delivery.telegraph import publish_article
    from src.output.render_report import render_report_html


LOGGER = logging.getLogger(__name__)
PROMPT_PATH = PROJECT_ROOT / "docs" / "prompts" / "study_plan.md"
OUTPUT_DIR = PROJECT_ROOT / "data" / "output" / "study_plans"
PROJECTS_YAML_PATH = PROJECT_ROOT / "src" / "config" / "projects.yaml"
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
def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat().replace("+00:00", "Z")


def _compute_week_label() -> str:
    year, week, _ = _utc_now().isocalendar()
    return f"{year}-W{week:02d}"


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
        SELECT posts.channel_username, posts.posted_at, posts.content, raw_posts.message_url
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
        suffix = f" | {row['message_url']}" if row["message_url"] else ""
        results.append(f"{row['channel_username']} | {row['posted_at'][:10]}: {content[:200]}{suffix}")
    return results


def _fetch_topics_this_week(connection: sqlite3.Connection, week_label: str) -> list[dict[str, Any]]:
    week_start_iso, week_end_iso = _week_bounds(week_label)
    rows = connection.execute(
        """
        SELECT t.label, t.description, COUNT(*) AS post_count
        FROM post_topics pt
        INNER JOIN topics t ON t.id = pt.topic_id
        INNER JOIN posts p ON p.id = pt.post_id
        WHERE p.posted_at >= ? AND p.posted_at < ?
        GROUP BY t.id, t.label, t.description
        ORDER BY post_count DESC
        LIMIT 10
        """,
        (week_start_iso, week_end_iso),
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


def _fetch_completed_study_history(connection: sqlite3.Connection, limit: int = 8) -> list[dict[str, str]]:
    rows = connection.execute(
        """
        SELECT week_label, topics_covered, COALESCE(completion_notes, '') AS completion_notes, completed_at
        FROM study_plans
        WHERE completed_at IS NOT NULL
        ORDER BY completed_at DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    history: list[dict[str, str]] = []
    for row in rows:
        try:
            topics = json.loads(row["topics_covered"] or "[]")
        except json.JSONDecodeError:
            topics = []
        history.append(
            {
                "week_label": str(row["week_label"] or ""),
                "topics": ", ".join(str(item) for item in topics if str(item).strip()),
                "notes": str(row["completion_notes"] or "").strip(),
                "completed_at": str(row["completed_at"] or ""),
            }
        )
    return history


def _fetch_active_projects(connection: sqlite3.Connection) -> list[str]:
    try:
        data = yaml.safe_load(PROJECTS_YAML_PATH.read_text(encoding="utf-8")) or {}
        projects = data.get("projects", [])
        lines = []
        for project in projects:
            if not isinstance(project, dict):
                continue
            name = str(project.get("name", "")).strip()
            focus = str(project.get("focus", "")).strip()
            if name:
                lines.append(f"{name}: {focus}")
        if lines:
            return lines[:8]
    except Exception:
        LOGGER.warning("Failed to load active projects from config; falling back to DB", exc_info=True)

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


def _fetch_project_context_snapshots(connection: sqlite3.Connection) -> list[dict[str, str]]:
    refresh_all_project_context_snapshots(connection)
    snapshots = load_project_context(connection)
    results: list[dict[str, str]] = []
    for item in snapshots[:8]:
        results.append(
            {
                "project_name": str(item.get("project_name") or ""),
                "summary": str(item.get("summary") or ""),
                "recent_changes": str(item.get("recent_changes") or ""),
                "open_questions": str(item.get("open_questions") or ""),
            }
        )
    return results


def _fetch_tagged_posts_this_week(connection: sqlite3.Connection, week_label: str, limit: int = 10) -> list[str]:
    week_start_iso, week_end_iso = _week_bounds(week_label)
    rows = connection.execute(
        """
        SELECT
            upt.tag,
            COALESCE(upt.note, '') AS note,
            p.channel_username,
            p.content,
            r.message_url
        FROM user_post_tags upt
        INNER JOIN posts p ON p.id = upt.post_id
        INNER JOIN raw_posts r ON r.id = p.raw_post_id
        WHERE p.posted_at >= ? AND p.posted_at < ?
        ORDER BY upt.recorded_at DESC, upt.id DESC
        LIMIT ?
        """,
        (week_start_iso, week_end_iso, limit),
    ).fetchall()
    results: list[str] = []
    for row in rows:
        excerpt = " ".join((row["content"] or "").split())[:220]
        note = str(row["note"] or "").strip()
        note_suffix = f" | note: {note}" if note else ""
        url = str(row["message_url"] or "").strip()
        url_suffix = f" | {url}" if url else ""
        results.append(f"{row['tag']} | {row['channel_username']}: {excerpt}{note_suffix}{url_suffix}")
    return results


def _fetch_acted_on_evidence(connection: sqlite3.Connection, limit: int = 10) -> list[str]:
    try:
        rows = fetch_decisions(
            connection,
            decision_scope="signal",
            status="acted_on",
            limit=limit,
        )
    except Exception:
        LOGGER.warning("Failed to load acted-on evidence for study plan", exc_info=True)
        return []
    results: list[str] = []
    for row in rows:
        ref_id = str(row.get("subject_ref_id") or "")
        reason = str(row.get("reason") or "")
        recorded_at = str(row.get("recorded_at") or "")[:10]
        results.append(f"[{recorded_at}] post_id={ref_id}: {reason}"[:200])
    return results


def _write_study_plan_file(week_label: str, content_md: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{week_label}.md"
    output_path.write_text(content_md, encoding="utf-8")
    return output_path


def generate_study_plan(settings: Settings, force: bool = False) -> str:
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
        if existing_row is not None and not force:
            content_md = str(existing_row["content_md"])
            if not output_path.exists():
                _write_study_plan_file(week_label, content_md)
            return content_md

        system_prompt, user_template = _load_prompt_sections()
        topics = _fetch_topics_this_week(connection, week_label)
        top_posts = _fetch_top_posts(connection, week_label)
        books_catalog = _fetch_books_catalog()
        projects = _fetch_active_projects(connection)
        project_context_snapshots = _fetch_project_context_snapshots(connection)
        previous_topics = _fetch_previous_plan_topics(connection)
        tagged_posts = _fetch_tagged_posts_this_week(connection, week_label)
        completed_history = _fetch_completed_study_history(connection)
        acted_on_evidence = _fetch_acted_on_evidence(connection)

        post_count = sum(int(topic.get("post_count") or 0) for topic in topics)
        prompt = (
            user_template.replace("{week_label}", week_label)
            .replace("{post_count}", str(post_count))
            .replace("{topics_json}", json.dumps(topics, ensure_ascii=True, indent=2))
            .replace("{top_posts}", json.dumps(top_posts, ensure_ascii=True, indent=2))
            .replace("{books_catalog}", json.dumps(books_catalog, ensure_ascii=True, indent=2))
            .replace("{projects_list}", json.dumps(projects, ensure_ascii=True, indent=2))
            .replace("{project_context_snapshots}", json.dumps(project_context_snapshots, ensure_ascii=True, indent=2))
            .replace("{previous_topics}", json.dumps(previous_topics, ensure_ascii=True))
            .replace("{tagged_posts}", json.dumps(tagged_posts, ensure_ascii=True, indent=2))
            .replace("{completed_history}", json.dumps(completed_history, ensure_ascii=True, indent=2))
            .replace("{acted_on_evidence}", json.dumps(acted_on_evidence, ensure_ascii=True, indent=2))
        )

        content_md = LLMClient.complete(
            prompt=prompt,
            system=system_prompt,
            max_tokens=3000,
            category="study_plan",
        )
        topics_covered = json.dumps([topic["label"] for topic in topics], ensure_ascii=True)

        connection.execute(
            """
            INSERT INTO study_plans (week_label, generated_at, content_md, topics_covered)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(week_label) DO UPDATE SET
                generated_at = excluded.generated_at,
                content_md = excluded.content_md,
                topics_covered = excluded.topics_covered
            """,
            (week_label, _utc_now_iso(), content_md, topics_covered),
        )
        connection.commit()

    output_path = _write_study_plan_file(week_label, content_md)
    LOGGER.info("Study plan generation complete week=%s output=%s", week_label, output_path)
    return content_md


def mark_study_complete(settings: Settings, week_label: str | None = None, notes: str | None = None) -> str:
    target_week = week_label or _compute_week_label()
    with sqlite3.connect(settings.db_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        connection.execute("PRAGMA journal_mode = WAL;")
        completed_at = _utc_now_iso()
        connection.execute(
            """
            INSERT INTO study_plans (week_label, generated_at, content_md, topics_covered, completed_at, completion_notes)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(week_label) DO UPDATE SET
                completed_at = excluded.completed_at,
                completion_notes = excluded.completion_notes
            """,
            (target_week, completed_at, "", "[]", completed_at, notes),
        )
        connection.commit()
    return target_week


def send_study_reminder(settings: Settings) -> None:
    try:
        week_label = _compute_week_label()
        with sqlite3.connect(settings.db_path) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON;")
            connection.execute("PRAGMA journal_mode = WAL;")
            row = connection.execute(
                """
                SELECT content_md, reminder_sent_at, completed_at
                FROM study_plans
                WHERE week_label = ?
                """,
                (week_label,),
            ).fetchone()

        if row is not None and row["completed_at"]:
            LOGGER.info("Study reminder skipped week=%s because the plan is already completed", week_label)
            return

        if row is not None and row["reminder_sent_at"]:
            LOGGER.info("Study reminder already sent week=%s", week_label)
            return

        content_md = str(row["content_md"]) if row is not None and row["content_md"] else generate_study_plan(settings)

        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.environ.get("TELEGRAM_OWNER_CHAT_ID", "").strip()
        if not bot_token or not chat_id:
            LOGGER.warning("Study reminder skipped because Telegram bot credentials are not configured")
            return

        telegraph_url: str | None = None
        notification = f"Study Plan {week_label} is ready.\nOpen the full plan:"
        try:
            html_content = render_report_html(content_md)
            telegraph_url = publish_article(title=f"Study Plan {week_label}", html_content=html_content)
            send_text(chat_id=chat_id, text=f"{notification}\n{telegraph_url}", token=bot_token, parse_mode=None)
            LOGGER.info("Study plan published to Telegraph week=%s url=%s", week_label, telegraph_url)
        except Exception:
            LOGGER.warning("Failed to publish study plan to Telegraph; falling back to text", exc_info=True)
            fallback = (
                f"Study plan for {week_label}\n"
                "Use /study_done when you finish this week's plan.\n\n"
                f"{content_md}"
            )
            send_text(chat_id=chat_id, text=fallback, token=bot_token)

        with sqlite3.connect(settings.db_path) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute(
                """
                UPDATE study_plans
                SET reminder_sent_at = ?, telegraph_url = ?
                WHERE week_label = ?
                """,
                (_utc_now_iso(), telegraph_url, week_label),
            )
            connection.commit()
        LOGGER.info("Study reminder sent week=%s", week_label)
    except Exception:
        LOGGER.warning("Failed to send study reminder", exc_info=True)
