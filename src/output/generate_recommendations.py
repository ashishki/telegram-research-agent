import logging
import os
import re
import sqlite3
from datetime import timezone, date, datetime, timedelta
from pathlib import Path

import yaml

from config.settings import PROJECT_ROOT, Settings
from llm.client import complete
from output.context_memory import load_project_context
from output.insight_triage import render_triaged_insights_html, triage_insights
from output.report_utils import _extract_markdown_section
from bot.telegram_delivery import send_text
from delivery.telegraph import publish_article


LOGGER = logging.getLogger(__name__)
PROMPT_PATH = PROJECT_ROOT / "docs" / "prompts" / "insights.md"
OUTPUT_DIR = PROJECT_ROOT / "data" / "output" / "recommendations"
PROJECTS_YAML_PATH = Path(__file__).resolve().parents[1] / "config" / "projects.yaml"
INLINE_URL_RE = re.compile(r"(?<![\"'>])(https?://[^\s<]+)")


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


def _load_project_context_snapshots(connection: sqlite3.Connection) -> str:
    snapshots = load_project_context(connection)
    if not snapshots:
        return "No project context snapshots available yet."
    lines: list[str] = []
    for item in snapshots:
        name = str(item.get("project_name") or "")
        summary = str(item.get("summary") or "")
        recent_changes = str(item.get("recent_changes") or "")
        open_questions = str(item.get("open_questions") or "")
        lines.append(f"{name}: {summary}")
        if recent_changes:
            lines.append(f"  recent_changes: {recent_changes}")
        if open_questions:
            lines.append(f"  open_questions: {open_questions}")
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


def _load_completed_study_history(connection: sqlite3.Connection, limit: int = 6) -> str:
    rows = connection.execute(
        """
        SELECT week_label, topics_covered, COALESCE(completion_notes, '') AS completion_notes
        FROM study_plans
        WHERE completed_at IS NOT NULL
        ORDER BY completed_at DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    lines: list[str] = []
    for row in rows:
        topics = row["topics_covered"] or "[]"
        notes = str(row["completion_notes"] or "").strip()
        line = f"{row['week_label']}: topics={topics}"
        if notes:
            line += f"; notes={notes}"
        lines.append(line)
    return "\n".join(lines) if lines else "No completed study history yet."


def _write_insights_file(week_label: str, content: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{week_label}_insights.md"
    output_path.write_text(content, encoding="utf-8")
    return output_path


def _write_insights_html_file(week_label: str, content_html: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{week_label}_insights.html"
    if "<html" in content_html.lower():
        html_content = content_html
    else:
        body_content = _render_insights_fragment(content_html)
        html_content = (
            "<html><head><meta charset=\"utf-8\"></head><body style=\"font-family: Georgia, serif; "
            "line-height: 1.68; color: #18212b; background: #f7f2e8; max-width: 860px; "
            "margin: 0 auto; padding: 20px;\">"
            "<style>"
            "body{font-size:17px;}"
            "section.idea{background:#fffdf8;border:1px solid #eadfcb;border-radius:16px;padding:18px 18px 8px 18px;margin:0 0 14px 0;}"
            "h2{font-size:22px;line-height:1.25;margin:0 0 12px 0;color:#102a43;}"
            "p{margin:0 0 12px 0;}"
            "a{color:#0b6bcb;text-decoration:none;}"
            "b{color:#0f1720;}"
            "</style>"
            f"<section class=\"idea\">{body_content}</section></body></html>"
        )
    output_path.write_text(html_content, encoding="utf-8")
    return output_path


def _render_insights_fragment(content: str) -> str:
    lines = [line.strip() for line in content.replace("\r\n", "\n").split("\n")]
    blocks: list[str] = []
    paragraph_parts: list[str] = []

    def flush_paragraph() -> None:
        if paragraph_parts:
            blocks.append(" ".join(paragraph_parts).strip())
            paragraph_parts.clear()

    for line in lines:
        if not line:
            flush_paragraph()
            continue
        if line.startswith("<b>") and line.endswith("</b>"):
            flush_paragraph()
            blocks.append(line)
            continue
        if line.startswith("<a ") and line.endswith("</a>"):
            paragraph_parts.append(line)
            flush_paragraph()
            continue
        paragraph_parts.append(line)
    flush_paragraph()

    rendered_blocks: list[str] = []
    for index, block in enumerate(blocks):
        normalized = _normalize_inline_html(block)
        if not normalized:
            continue
        if normalized.startswith("<b>") and normalized.endswith("</b>"):
            tag = "h2" if index == 0 else "p"
            rendered_blocks.append(f"<{tag}>{normalized}</{tag}>")
            continue
        if normalized.startswith("<a ") and normalized.endswith("</a>"):
            rendered_blocks.append(f"<p>{normalized}</p>")
            continue
        rendered_blocks.append(f"<p>{normalized}</p>")
    return "\n".join(rendered_blocks)


def _normalize_inline_html(text: str) -> str:
    normalized = text.strip()
    normalized = INLINE_URL_RE.sub(r'<a href="\1">\1</a>', normalized)
    return normalized


def _load_delivery_state(connection: sqlite3.Connection, week_label: str) -> dict[str, str]:
    row = connection.execute(
        """
        SELECT COALESCE(telegraph_url, '') AS telegraph_url,
               COALESCE(telegram_sent_at, '') AS telegram_sent_at
        FROM recommendations
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
        f"UPDATE recommendations SET {', '.join(fields)} WHERE week_label = ?",
        params,
    )


def _store_recommendations(connection: sqlite3.Connection, week_label: str, content_md: str) -> None:
    connection.execute(
        """
        INSERT INTO recommendations (week_label, generated_at, content_md)
        VALUES (?, ?, ?)
        ON CONFLICT(week_label) DO UPDATE SET
            generated_at = excluded.generated_at,
            content_md = excluded.content_md
        """,
        (week_label, _utc_now_iso(), content_md),
    )


def _build_notification(week_label: str) -> str:
    return (
        f"Implementation Ideas {week_label} is ready.\n"
        "Open the full brief:"
    )[:300]


def _send_recommendations_to_telegram_owner(
    connection: sqlite3.Connection,
    week_label: str,
    content_md: str,
    html_path: Path | None,
    force_delivery: bool = False,
) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_OWNER_CHAT_ID", "").strip()
    if not token or not chat_id:
        return
    delivery_state = _load_delivery_state(connection, week_label)
    if delivery_state["telegram_sent_at"] and not force_delivery:
        LOGGER.info("Implementation ideas delivery skipped week=%s because it was already sent", week_label)
        return
    notification = _build_notification(week_label)
    if html_path is not None:
        try:
            html_content = html_path.read_text(encoding="utf-8")
            url = publish_article(title=f"Implementation Ideas {week_label}", html_content=html_content)
            send_text(chat_id=chat_id, text=f"{notification}\n{url}", token=token, parse_mode=None)
            _mark_delivery_state(connection, week_label, telegraph_url=url, telegram_sent_at=_utc_now_iso())
            connection.commit()
            LOGGER.info("Implementation ideas published to Telegraph week=%s url=%s", week_label, url)
            return
        except Exception:
            LOGGER.warning("Failed to publish implementation ideas week=%s", week_label, exc_info=True)
    send_text(chat_id=chat_id, text=notification, token=token, parse_mode=None)
    _mark_delivery_state(connection, week_label, telegram_sent_at=_utc_now_iso())
    connection.commit()


def run_recommendations(settings: Settings, force_delivery: bool = False) -> dict:
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
        project_context_snapshots = _load_project_context_snapshots(connection)
        completed_study_history = _load_completed_study_history(connection)
        system_prompt, user_template = _load_prompt_sections()
        prompt = (
            user_template.replace("{week_label}", week_label)
            .replace("{digest_summary}", digest_summary)
            .replace("{projects_context}", projects_context)
            .replace("{project_context_snapshots}", project_context_snapshots)
            .replace("{completed_study_history}", completed_study_history)
        )

        insights_text = complete(prompt=prompt, system=system_prompt, category="insight")

        # Triage: classify ideas and apply rejection memory before rendering
        connection.execute("BEGIN")
        triaged = triage_insights(insights_text, connection, week_label)
        connection.commit()

        delivery_text = render_triaged_insights_html(insights_text, triaged)

        output_path = _write_insights_file(week_label, delivery_text)
        html_path = _write_insights_html_file(week_label, delivery_text)
        connection.execute("BEGIN")
        _store_recommendations(connection, week_label, delivery_text)
        connection.commit()
        try:
            _send_recommendations_to_telegram_owner(
                connection=connection,
                week_label=week_label,
                content_md=delivery_text,
                html_path=html_path,
                force_delivery=force_delivery,
            )
        except Exception:
            LOGGER.warning("Failed to send implementation ideas week=%s", week_label, exc_info=True)

    LOGGER.info(
        "Insights generation complete week=%s output=%s",
        week_label,
        output_path,
    )
    return {"week_label": week_label, "output_path": str(output_path), "text": delivery_text, "html_path": str(html_path)}


def generate_recommendations(settings: Settings) -> dict:
    return run_recommendations(settings)
