import json
import logging
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config.settings import PROJECT_ROOT
from llm.client import LLMClient


LOGGER = logging.getLogger(__name__)
PROMPT_PATH = PROJECT_ROOT / "docs" / "prompts" / "github_insights.md"
OUTPUT_DIR = PROJECT_ROOT / "data" / "output" / "insights"
POST_LIMIT = 20


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat().replace("+00:00", "Z")


def _compute_week_label(now: datetime | None = None) -> str:
    current = now or _utc_now()
    year, week, _ = current.isocalendar()
    return f"{year}-W{week:02d}"


def _extract_markdown_section(text: str, heading: str) -> str:
    pattern = re.compile(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)
    match = pattern.search(text)
    if not match:
        raise ValueError(f"Section not found in prompt file: {heading}")
    return match.group(1).strip()


def _load_prompt_template() -> str:
    prompt_markdown = PROMPT_PATH.read_text(encoding="utf-8")
    return _extract_markdown_section(prompt_markdown, "User Prompt Template")


def _parse_keywords(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return [part.strip() for part in value.split(",") if part.strip()]
    if not isinstance(decoded, list):
        return []
    return [str(item).strip() for item in decoded if str(item).strip()]


def _escape_fts_term(term: str) -> str:
    return term.replace('"', " ").strip()


def _search_project_posts(
    connection: sqlite3.Connection,
    keywords: list[str],
    cutoff_iso: str,
) -> list[sqlite3.Row]:
    seen_ids: set[int] = set()
    matched_rows: list[sqlite3.Row] = []

    for keyword in keywords:
        escaped = _escape_fts_term(keyword)
        if not escaped:
            continue
        rows = connection.execute(
            """
            SELECT posts.id, posts.posted_at, posts.channel_username, posts.content
            FROM posts_fts
            INNER JOIN posts ON posts.id = posts_fts.rowid
            WHERE posts_fts MATCH ? AND posts.posted_at >= ?
            ORDER BY posts.posted_at DESC, posts.id DESC
            LIMIT ?
            """,
            (f'"{escaped}"', cutoff_iso, POST_LIMIT),
        ).fetchall()
        for row in rows:
            if row["id"] in seen_ids:
                continue
            seen_ids.add(row["id"])
            matched_rows.append(row)
            if len(matched_rows) >= POST_LIMIT:
                return matched_rows

    return matched_rows


def _format_posts_excerpt(rows: list[sqlite3.Row]) -> str:
    lines = []
    for row in rows:
        excerpt = " ".join((row["content"] or "").split())[:220]
        lines.append(f"- {row['posted_at']}: {excerpt}")
    return "\n".join(lines)


def _write_output_file(week_label: str, content_md: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{week_label}.md"
    output_path.write_text(content_md, encoding="utf-8")
    return output_path


def generate_insight(db_path: str, lookback_days: int = 90) -> str:
    cutoff_iso = (_utc_now() - timedelta(days=lookback_days)).isoformat().replace("+00:00", "Z")
    prompt_template = _load_prompt_template()
    week_label = _compute_week_label()

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        connection.execute("PRAGMA journal_mode = WAL;")

        projects = connection.execute(
            """
            SELECT id, name, description, keywords, github_repo, last_commit_at, github_synced_at
            FROM projects
            WHERE active = 1
            ORDER BY name ASC
            """
        ).fetchall()
        if not projects:
            LOGGER.info("Insight generation skipped: no active projects")
            return ""

        sections = [f"# Retroactive Project Insights — {week_label}", f"_Generated at {_utc_now_iso()}_\n"]

        for project in projects:
            keywords = _parse_keywords(project["keywords"])
            if not keywords:
                LOGGER.info("Skipping insight generation for project=%s because it has no keywords", project["name"])
                continue

            matched_rows = _search_project_posts(connection, keywords, cutoff_iso)
            if not matched_rows:
                LOGGER.info("No historical Telegram matches for project=%s", project["name"])
                continue

            prompt = (
                prompt_template.replace("{PROJECT_NAME}", project["name"])
                .replace("{PROJECT_DESCRIPTION}", project["description"] or "")
                .replace("{PROJECT_KEYWORDS}", json.dumps(keywords, ensure_ascii=True))
                .replace("{POSTS_EXCERPT}", _format_posts_excerpt(matched_rows))
            )
            try:
                insight_md = LLMClient.complete(prompt=prompt)
            except Exception:
                LOGGER.warning("LLM insight generation failed for project=%s", project["name"], exc_info=True)
                continue

            sections.append(f"## {project['name']}\n")
            sections.append(insight_md.strip())
            sections.append("")

    output_md = "\n".join(section for section in sections if section is not None).strip() + "\n"
    output_path = _write_output_file(week_label, output_md)
    LOGGER.info("Insight generation complete output=%s", output_path)
    return output_md
