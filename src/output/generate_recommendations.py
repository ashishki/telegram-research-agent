import logging
import sqlite3
from datetime import timezone, date, datetime, timedelta
from pathlib import Path

import yaml

from config.settings import PROJECT_ROOT, Settings
from llm.client import complete
from output.report_utils import _extract_markdown_section


LOGGER = logging.getLogger(__name__)
PROMPT_PATH = PROJECT_ROOT / "docs" / "prompts" / "insights.md"
OUTPUT_DIR = PROJECT_ROOT / "data" / "output" / "recommendations"
PROJECTS_YAML_PATH = Path(__file__).resolve().parents[2] / "config" / "projects.yaml"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat().replace("+00:00", "Z")


def _compute_week_label(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    year, week, _ = current.isocalendar()
    return f"{year}-W{week:02d}"


def _week_start(week_label: str) -> datetime:
    year_str, week_str = week_label.split("-W", maxsplit=1)
    week_date = date.fromisocalendar(int(year_str), int(week_str), 1)
    return datetime.combine(week_date, datetime.min.time(), tzinfo=timezone.utc)


def _week_bounds(week_label: str) -> tuple[str, str]:
    start = _week_start(week_label)
    end = start + timedelta(days=7)
    return (
        start.isoformat().replace("+00:00", "Z"),
        end.isoformat().replace("+00:00", "Z"),
    )


def _load_prompt_sections() -> tuple[str, str]:
    prompt_markdown = PROMPT_PATH.read_text(encoding="utf-8")
    system_prompt = _extract_markdown_section(prompt_markdown, "System Prompt")
    user_template = _extract_markdown_section(prompt_markdown, "User Prompt Template")
    return system_prompt, user_template


def _load_projects_context() -> str:
    data = yaml.safe_load(PROJECTS_YAML_PATH.read_text(encoding="utf-8"))
    projects = data.get("projects", [])
    lines = []
    for project in projects:
        name = project.get("name", "")
        description = project.get("description", "")
        focus = project.get("focus", "")
        lines.append(f"{name}: {description}. Фокус: {focus}")
    return "\n".join(lines)


def _load_digest_summary(connection: sqlite3.Connection, week_label: str) -> tuple[str | None, str]:
    row = connection.execute(
        """
        SELECT content_md
        FROM digests
        WHERE week_label = ?
        """,
        (week_label,),
    ).fetchone()
    if row is None:
        return None, ""
    digest_md = row["content_md"]

    week_start_iso, week_end_iso = _week_bounds(week_label)
    topic_rows = connection.execute(
        """
        SELECT topics.label, COUNT(*) AS post_count
        FROM post_topics
        INNER JOIN topics ON topics.id = post_topics.topic_id
        INNER JOIN posts ON posts.id = post_topics.post_id
        WHERE posts.posted_at >= ? AND posts.posted_at < ?
        GROUP BY topics.id, topics.label
        ORDER BY post_count DESC, topics.label ASC
        LIMIT 10
        """,
        (week_start_iso, week_end_iso),
    ).fetchall()

    notable_rows = connection.execute(
        """
        SELECT
            posts.channel_username,
            posts.content,
            raw_posts.message_url,
            COALESCE(raw_posts.view_count, 0) AS view_count
        FROM posts
        INNER JOIN raw_posts ON raw_posts.id = posts.raw_post_id
        WHERE posts.posted_at >= ? AND posts.posted_at < ?
        ORDER BY view_count DESC, posts.posted_at DESC
        LIMIT 10
        """,
        (week_start_iso, week_end_iso),
    ).fetchall()

    lines = []
    if topic_rows:
        lines.append("Топ тем:")
        for row in topic_rows:
            lines.append(f"  - {row['label']} ({row['post_count']} постов)")

    if notable_rows:
        lines.append("\nПримечательные посты:")
        for row in notable_rows:
            excerpt = " ".join((row["content"] or "").split())[:200]
            url = row["message_url"] or ""
            channel = row["channel_username"] or ""
            lines.append(f"  - [{channel}] {excerpt} {url}".strip())

    return digest_md, "\n".join(lines)


def _write_insights_file(week_label: str, content: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{week_label}_insights.md"
    output_path.write_text(content, encoding="utf-8")
    return output_path


def _store_recommendations(connection: sqlite3.Connection, week_label: str, content_md: str) -> None:
    connection.execute(
        """
        INSERT OR REPLACE INTO recommendations (week_label, generated_at, content_md)
        VALUES (?, ?, ?)
        """,
        (week_label, _utc_now_iso(), content_md),
    )


def run_recommendations(settings: Settings) -> dict:
    week_label = _compute_week_label()
    db_path = settings.db_path

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        connection.execute("PRAGMA journal_mode = WAL;")

        digest_md, digest_summary = _load_digest_summary(connection, week_label)
        if digest_md is None:
            LOGGER.warning("Insights skipped because no digest exists for week=%s", week_label)
            return {"week_label": week_label, "output_path": None, "text": ""}

        projects_context = _load_projects_context()
        system_prompt, user_template = _load_prompt_sections()
        prompt = (
            user_template.replace("{week_label}", week_label)
            .replace("{digest_summary}", digest_summary)
            .replace("{projects_context}", projects_context)
        )

        insights_text = complete(prompt=prompt, system=system_prompt, category="insight")

        output_path = _write_insights_file(week_label, insights_text)
        connection.execute("BEGIN")
        _store_recommendations(connection, week_label, insights_text)
        connection.commit()

    LOGGER.info(
        "Insights generation complete week=%s output=%s",
        week_label,
        output_path,
    )
    return {"week_label": week_label, "output_path": str(output_path), "text": insights_text}


def generate_recommendations(settings: Settings) -> dict:
    return run_recommendations(settings)
