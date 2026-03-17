import json
import logging
import sqlite3
from datetime import timezone, datetime, timedelta
from pathlib import Path
from typing import Any

from config.settings import PROJECT_ROOT, Settings
from llm.client import LLMError, LLMSchemaError, complete_json
from output.report_utils import _extract_markdown_section


LOGGER = logging.getLogger(__name__)
PROMPT_PATH = PROJECT_ROOT / "docs" / "prompts" / "project_insights.md"
PROJECT_INSIGHTS_OUTPUT_DIR = PROJECT_ROOT / "data" / "output" / "project_insights"
TEXT_EXCERPT_LENGTH = 200
FTS_MATCH_LIMIT = 20
LLM_POST_LIMIT = 10
MAX_VIEW_COUNT = 10000


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _compute_week_label(now: datetime | None = None) -> str:
    current = now or _utc_now()
    year, week, _ = current.isocalendar()
    return f"{year}-W{week:02d}"


def _start_of_current_iso_week(now: datetime | None = None) -> datetime:
    current = now or _utc_now()
    return current - timedelta(
        days=current.isoweekday() - 1,
        hours=current.hour,
        minutes=current.minute,
        seconds=current.second,
        microseconds=current.microsecond,
    )


def _load_prompt_sections() -> tuple[str, str]:
    prompt_markdown = PROMPT_PATH.read_text(encoding="utf-8")
    system_prompt = _extract_markdown_section(prompt_markdown, "System Prompt")
    user_template = _extract_markdown_section(prompt_markdown, "User Prompt Template")
    return system_prompt, user_template


def _split_keywords(keywords: str | None) -> list[str]:
    if not keywords:
        return []
    try:
        parsed = json.loads(keywords)
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    except (json.JSONDecodeError, ValueError):
        pass
    values = [part.strip() for part in keywords.split(",")]
    return [value for value in values if value]


def _build_fts_query(keywords: list[str]) -> str:
    return " OR ".join(f'"{keyword.replace(chr(34), " ").strip()}"' for keyword in keywords if keyword.strip())


def _make_excerpt(text: str | None) -> str:
    compact = " ".join((text or "").split())
    return compact[:TEXT_EXCERPT_LENGTH]


def _keyword_match_count(content: str | None, keywords: list[str]) -> int:
    lowered_content = (content or "").lower()
    return sum(1 for keyword in keywords if keyword.lower() in lowered_content)


def _coerce_view_count(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _score_post(row: sqlite3.Row, keywords: list[str]) -> dict[str, Any]:
    match_count = _keyword_match_count(row["content"], keywords)
    total_keywords = len(keywords)
    relevance_score_base = match_count / total_keywords if total_keywords else 0.0
    view_count = _coerce_view_count(row["view_count"])
    final_score = relevance_score_base * 0.7 + (min(view_count, MAX_VIEW_COUNT) / MAX_VIEW_COUNT) * 0.3
    return {
        "post_id": row["id"],
        "channel_username": row["channel_username"],
        "content": row["content"] or "",
        "text_excerpt": _make_excerpt(row["content"]),
        "view_count": view_count,
        "message_url": row["message_url"],
        "topic_label": "",
        "final_score": final_score,
    }


def _search_project_posts(
    connection: sqlite3.Connection,
    keywords: list[str],
    week_start_iso: str,
) -> list[sqlite3.Row]:
    if not keywords:
        return []

    fts_query = _build_fts_query(keywords)
    if not fts_query:
        return []

    return connection.execute(
        """
        SELECT posts.id, posts.content, posts.channel_username, raw_posts.view_count, raw_posts.message_url
        FROM posts_fts
        JOIN posts ON posts.id = posts_fts.rowid
        JOIN raw_posts ON raw_posts.id = posts.raw_post_id
        WHERE posts_fts MATCH ? AND posts.posted_at >= ?
        ORDER BY raw_posts.view_count DESC
        LIMIT ?
        """,
        (fts_query, week_start_iso, FTS_MATCH_LIMIT),
    ).fetchall()


def _render_user_prompt(
    user_template: str,
    project: sqlite3.Row,
    matched_posts: list[dict[str, Any]],
) -> str:
    prompt_posts = [
        {
            "post_id": post["post_id"],
            "channel_username": post["channel_username"],
            "text_excerpt": post["text_excerpt"],
            "view_count": post["view_count"],
            "message_url": post["message_url"],
            "topic_label": post["topic_label"],
        }
        for post in matched_posts
    ]
    return (
        user_template.replace("{project_name}", project["name"])
        .replace("{project_description}", project["description"] or "")
        .replace("{project_keywords}", project["keywords"] or "")
        .replace("{matched_posts}", json.dumps(prompt_posts, ensure_ascii=True))
    )


def _coerce_llm_response(response: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
    if not isinstance(response, list):
        raise LLMSchemaError("Project insights response must be a JSON array")

    entries: list[dict[str, Any]] = []
    for item in response:
        if not isinstance(item, dict):
            continue

        try:
            post_id = int(item.get("post_id"))
        except (TypeError, ValueError):
            continue

        try:
            relevance_score = float(item.get("relevance_score", 0.0))
        except (TypeError, ValueError):
            relevance_score = 0.0

        rationale = item.get("rationale")
        rationale_text = str(rationale).strip() if rationale is not None else None

        entries.append(
            {
                "post_id": post_id,
                "relevant": bool(item.get("relevant")),
                "relevance_score": relevance_score,
                "rationale": rationale_text,
            }
        )

    return entries


def _insert_project_links(
    connection: sqlite3.Connection,
    project_id: int,
    relevant_entries: list[dict[str, Any]],
) -> int:
    if not relevant_entries:
        return 0

    rows = [
        (
            entry["post_id"],
            project_id,
            entry["relevance_score"],
            entry["rationale"],
        )
        for entry in relevant_entries
    ]
    cursor = connection.executemany(
        """
        INSERT OR IGNORE INTO post_project_links (post_id, project_id, relevance_score, note)
        VALUES (?, ?, ?, ?)
        """,
        rows,
    )
    return cursor.rowcount if cursor.rowcount != -1 else 0


def _render_project_insights_report(week_label: str, project_notes: dict[str, list[str]]) -> str:
    lines = [f"## Project Insights — {week_label}", ""]
    if not project_notes:
        lines.append("No project insights were identified this week.")
        return "\n".join(lines).rstrip() + "\n"

    for project_name, notes in project_notes.items():
        if not notes:
            continue
        lines.append(f"### {project_name}")
        lines.extend(f"- {note}" for note in notes)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _write_project_insights_file(week_label: str, content_md: str) -> Path:
    PROJECT_INSIGHTS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = PROJECT_INSIGHTS_OUTPUT_DIR / f"{week_label}.md"
    output_path.write_text(content_md, encoding="utf-8")
    return output_path


def run_project_mapping(settings: Settings) -> dict:
    result = {"projects_processed": 0, "links_created": 0, "output_path": None}
    week_label = _compute_week_label()
    week_start_iso = _start_of_current_iso_week().isoformat().replace("+00:00", "Z")
    project_notes: dict[str, list[str]] = {}

    with sqlite3.connect(settings.db_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        connection.execute("PRAGMA journal_mode = WAL;")

        projects = connection.execute(
            """
            SELECT id, name, description, keywords
            FROM projects
            WHERE active = 1
            ORDER BY name ASC
            """
        ).fetchall()

        if not projects:
            LOGGER.info("Project mapping found no active projects for week=%s", week_label)
        else:
            system_prompt, user_template = _load_prompt_sections()

            for project in projects:
                result["projects_processed"] += 1
                keywords = _split_keywords(project["keywords"])
                if not keywords:
                    LOGGER.info(
                        "Skipping project_id=%d name=%r because it has no keywords",
                        project["id"],
                        project["name"],
                    )
                    continue

                matched_rows = _search_project_posts(connection, keywords, week_start_iso)
                if not matched_rows:
                    LOGGER.info("No keyword matches for project_id=%d name=%r", project["id"], project["name"])
                    continue

                scored_posts = [_score_post(row, keywords) for row in matched_rows]
                ranked_posts = sorted(
                    scored_posts,
                    key=lambda post: (-post["final_score"], -post["view_count"], post["post_id"]),
                )
                top_posts = ranked_posts[:LLM_POST_LIMIT]

                prompt = _render_user_prompt(user_template=user_template, project=project, matched_posts=top_posts)

                try:
                    raw_response = complete_json(prompt=prompt, system=system_prompt, category="project_insights")
                except (LLMError, LLMSchemaError):
                    LOGGER.warning(
                        "Project insight LLM call failed for project_id=%d; returning empty",
                        project["id"],
                        exc_info=True,
                    )
                    project_notes[project["name"]] = []
                    continue

                if not isinstance(raw_response, list):
                    LOGGER.warning(
                        "Project insight LLM response is not a list for project_id=%d type=%s; returning empty",
                        project["id"],
                        type(raw_response).__name__,
                    )
                    project_notes[project["name"]] = []
                    continue

                try:
                    response = _coerce_llm_response(raw_response)
                except (LLMSchemaError, ValueError):
                    LOGGER.warning(
                        "Project insight LLM response coercion failed for project_id=%d; returning empty",
                        project["id"],
                        exc_info=True,
                    )
                    project_notes[project["name"]] = []
                    continue

                allowed_post_ids = {post["post_id"] for post in top_posts}
                relevant_entries = [
                    entry
                    for entry in response
                    if entry["post_id"] in allowed_post_ids
                    and entry["relevant"]
                    and entry["relevance_score"] >= 0.4
                    and entry["rationale"]
                ]

                try:
                    connection.execute("BEGIN")
                    inserted_count = _insert_project_links(connection, project["id"], relevant_entries)
                    connection.commit()
                except Exception:
                    connection.rollback()
                    LOGGER.exception("Failed to persist project links for project_id=%d", project["id"])
                    continue

                if relevant_entries:
                    project_notes[project["name"]] = [entry["rationale"] for entry in relevant_entries if entry["rationale"]]

                result["links_created"] += inserted_count
                LOGGER.info(
                    "Project mapping complete for project_id=%d name=%r matched=%d relevant=%d inserted=%d",
                    project["id"],
                    project["name"],
                    len(matched_rows),
                    len(relevant_entries),
                    inserted_count,
                )

    content_md = _render_project_insights_report(week_label, project_notes)
    output_path = _write_project_insights_file(week_label, content_md)
    LOGGER.info("Project insights report written week=%s output=%s", week_label, output_path)
    result["output_path"] = str(output_path)
    return result
