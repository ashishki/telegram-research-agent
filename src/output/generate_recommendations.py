import json
import logging
import re
import sqlite3
from datetime import timezone, date, datetime, timedelta
from pathlib import Path

from config.settings import PROJECT_ROOT, Settings
from db.migrate import get_db_path
from llm.client import complete


LOGGER = logging.getLogger(__name__)
PROMPT_PATH = PROJECT_ROOT / "docs" / "prompts" / "recommendations.md"
OUTPUT_DIR = PROJECT_ROOT / "data" / "output" / "recommendations"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat().replace("+00:00", "Z")


def _compute_week_label(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    year, week, _ = current.isocalendar()
    return f"{year}-W{week:02d}"


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


def _previous_week_label(week_label: str) -> str:
    previous = _week_start(week_label) - timedelta(days=7)
    year, week, _ = previous.isocalendar()
    return f"{year}-W{week:02d}"


def _write_recommendations_file(week_label: str, content_md: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{week_label}.md"
    output_path.write_text(content_md, encoding="utf-8")
    return output_path


def _extract_recommendation_labels(content_md: str) -> list[str]:
    labels = re.findall(r"^###\s+\d+\.\s+(.+?)\s*$", content_md, flags=re.MULTILINE)
    return labels


def _load_this_week_topics(connection: sqlite3.Connection, week_label: str) -> list[dict]:
    week_start_iso, week_end_iso = _week_bounds(week_label)
    rows = connection.execute(
        """
        SELECT topics.label, COUNT(*) AS post_count
        FROM post_topics
        INNER JOIN topics ON topics.id = post_topics.topic_id
        INNER JOIN posts ON posts.id = post_topics.post_id
        WHERE posts.posted_at >= ? AND posts.posted_at < ?
        GROUP BY topics.id, topics.label
        ORDER BY post_count DESC, topics.label ASC
        """,
        (week_start_iso, week_end_iso),
    ).fetchall()
    return [{"label": row["label"], "post_count": row["post_count"]} for row in rows]


def _load_recurring_topics(connection: sqlite3.Connection, week_label: str) -> list[dict]:
    week_starts = [_week_start(week_label) - timedelta(days=7 * offset) for offset in range(4)]
    week_ranges = []
    for index, start in enumerate(week_starts):
        week_ranges.extend(
            [
                start.isoformat().replace("+00:00", "Z"),
                (start + timedelta(days=7)).isoformat().replace("+00:00", "Z"),
                f"week_{index}",
            ]
        )
    rows = connection.execute(
        """
        WITH bucketed_topic_posts AS (
            SELECT
                topics.id AS topic_id,
                topics.label AS label,
                topics.description AS description,
                CASE
                    WHEN posts.posted_at >= ? AND posts.posted_at < ? THEN ?
                    WHEN posts.posted_at >= ? AND posts.posted_at < ? THEN ?
                    WHEN posts.posted_at >= ? AND posts.posted_at < ? THEN ?
                    WHEN posts.posted_at >= ? AND posts.posted_at < ? THEN ?
                END AS week_bucket
            FROM post_topics
            INNER JOIN topics ON topics.id = post_topics.topic_id
            INNER JOIN posts ON posts.id = post_topics.post_id
        ),
        weekly_topic_counts AS (
            SELECT
                topic_id,
                label,
                description,
                week_bucket,
                COUNT(*) AS weekly_post_count
            FROM bucketed_topic_posts
            WHERE week_bucket IS NOT NULL
            GROUP BY topic_id, label, description, week_bucket
        )
        SELECT
            label,
            description,
            COUNT(*) AS week_count,
            SUM(weekly_post_count) AS total_post_count
        FROM weekly_topic_counts
        GROUP BY topic_id, label, description
        HAVING COUNT(*) >= 3
        ORDER BY week_count DESC, total_post_count DESC, label ASC
        """,
        tuple(week_ranges),
    ).fetchall()
    return [
        {
            "label": row["label"],
            "description": row["description"],
            "week_count": row["week_count"],
            "total_post_count": row["total_post_count"],
        }
        for row in rows
    ]


def _load_active_projects(connection: sqlite3.Connection) -> list[dict]:
    rows = connection.execute(
        """
        SELECT name, description, keywords
        FROM projects
        WHERE active = 1
        ORDER BY name ASC
        """
    ).fetchall()
    return [
        {
            "name": row["name"],
            "description": row["description"],
            "keywords": row["keywords"],
        }
        for row in rows
    ]


def _load_last_recommendations(connection: sqlite3.Connection, week_label: str) -> list[str]:
    previous_week_label = _previous_week_label(week_label)
    row = connection.execute(
        """
        SELECT content_md
        FROM recommendations
        WHERE week_label = ?
        """,
        (previous_week_label,),
    ).fetchone()
    if row is None:
        return []
    return _extract_recommendation_labels(row["content_md"])


def _store_recommendations(connection: sqlite3.Connection, week_label: str, content_md: str) -> None:
    connection.execute(
        """
        INSERT OR REPLACE INTO recommendations (week_label, generated_at, content_md)
        VALUES (?, ?, ?)
        """,
        (week_label, _utc_now_iso(), content_md),
    )


def run_recommendations(settings: Settings) -> dict:
    del settings

    week_label = _compute_week_label()
    db_path = get_db_path()

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        connection.execute("PRAGMA journal_mode = WAL;")

        digest_row = connection.execute(
            """
            SELECT content_md
            FROM digests
            WHERE week_label = ?
            """,
            (week_label,),
        ).fetchone()
        if digest_row is None:
            LOGGER.warning("Recommendations skipped because no digest exists for week=%s", week_label)
            return {"week_label": week_label, "output_path": None}

        this_week_topics = _load_this_week_topics(connection, week_label)
        recurring_topics = _load_recurring_topics(connection, week_label)
        active_projects = _load_active_projects(connection)
        last_recommendations = _load_last_recommendations(connection, week_label)

        system_prompt, user_template = _load_prompt_sections()
        prompt = (
            user_template.replace("{week_label}", week_label)
            .replace("{this_week_topics}", json.dumps(this_week_topics, ensure_ascii=True))
            .replace("{recurring_topics}", json.dumps(recurring_topics, ensure_ascii=True))
            .replace("{active_projects}", json.dumps(active_projects, ensure_ascii=True))
            .replace("{last_recommendations}", json.dumps(last_recommendations, ensure_ascii=True))
        )

        content_md = complete(prompt=prompt, system=system_prompt, category="recommendations")
        if not content_md.lstrip().startswith(f"## Study Recommendations — {week_label}"):
            LOGGER.warning("Recommendations response did not match expected heading for week=%s", week_label)

        output_path = _write_recommendations_file(week_label, content_md)
        connection.execute("BEGIN")
        _store_recommendations(connection, week_label, content_md)
        connection.commit()

    LOGGER.info(
        "Recommendations generation complete week=%s output=%s digest_length=%d",
        week_label,
        output_path,
        len(digest_row["content_md"]),
    )
    return {"week_label": week_label, "output_path": str(output_path)}


def generate_recommendations(settings: Settings) -> dict:
    return run_recommendations(settings)
