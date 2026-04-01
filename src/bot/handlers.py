import logging
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from urllib import error

from bot.telegram_delivery import _send_text_internal, send_document, send_report_preview, send_text
from config.settings import PROJECT_ROOT, Settings
from db.migrate import record_feedback, record_post_tag
from output.generate_digest import _compute_week_label, run_digest
from output.generate_answer import generate_answer
from output.generate_insight import generate_insight
from output.generate_study_plan import generate_study_plan, mark_study_complete


LOGGER = logging.getLogger(__name__)
QUESTION_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)
TELEGRAM_POST_URL_RE = re.compile(r"^https?://t\.me/([A-Za-z0-9_]+)/(\d+)(?:\?.*)?$", re.IGNORECASE)
MARKDOWN_V2_SPECIAL_CHARS = r"_*[]()~`>#+-=|{}.!"
COMMAND_DOCS: dict[str, tuple[str, str]] = {
    "/digest": ("handle_digest", "Show the current weekly brief"),
    "/topics": ("handle_topics", "List the strongest tracked topics"),
    "/insight": ("handle_insight", "Show retrospective project insights"),
    "/project <name>": ("handle_project", "Find an active project by partial name"),
    "/ask <question>": ("handle_ask", "Answer a question from the last 7 days of Telegram data"),
    "/study [refresh]": ("handle_study", "Show the weekly study plan or rebuild it"),
    "/study_done [notes]": ("handle_study_done", "Mark this week's study plan as completed"),
    "/costs": ("handle_costs", "Show LLM usage and cost statistics"),
    "/run_digest [force]": ("handle_run_digest", "Generate a fresh weekly brief; use force to resend delivery for the same week"),
    "/status": ("handle_status", "Show database and pipeline status"),
    "/mark_useful <post_id|link>": ("handle_mark_useful", "Record acted_on feedback"),
    "/mark_skipped <post_id|link>": ("handle_mark_skipped", "Record skipped feedback"),
    "/tag <post_id|link> <tag>": ("handle_tag", "Save a tag: strong, interesting, try, funny, low, later"),
    "/mark_strong <post_id|link>": ("handle_mark_strong", "Mark a post as strong"),
    "/mark_interesting <post_id|link>": ("handle_mark_interesting", "Mark a post as interesting"),
    "/mark_try <post_id|link>": ("handle_mark_try", "Mark a post as worth trying in a project"),
    "/mark_funny <post_id|link>": ("handle_mark_funny", "Mark a post as cultural or funny"),
    "/mark_low <post_id|link>": ("handle_mark_low", "Mark a post as low signal"),
    "/mark_later <post_id|link>": ("handle_mark_later", "Mark a post to revisit later"),
}

TAG_ALIASES = {
    "strong": "strong",
    "interesting": "interesting",
    "try": "try_in_project",
    "try_in_project": "try_in_project",
    "funny": "funny",
    "low": "low_signal",
    "low_signal": "low_signal",
    "later": "read_later",
    "read_later": "read_later",
}


def _get_bot_token() -> str:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()


def _escape_markdown_v2(text: str) -> str:
    escaped = []
    for char in text:
        if char in MARKDOWN_V2_SPECIAL_CHARS:
            escaped.append(f"\\{char}")
        else:
            escaped.append(char)
    return "".join(escaped)


def send_message(
    token: str,
    chat_id: str,
    text: str,
    parse_mode: str | None = "MarkdownV2",
    escape_markdown: bool = True,
) -> None:
    message_text = _escape_markdown_v2(text) if escape_markdown else text
    try:
        _send_text_internal(chat_id=chat_id, text=message_text, token=token, parse_mode=parse_mode)
    except Exception:
        LOGGER.warning("Failed to send Telegram message to chat_id=%s", chat_id, exc_info=True)


def send_file(token: str, chat_id: str, filepath: str, caption: str = "") -> None:
    try:
        send_document(chat_id=chat_id, file_path=filepath, caption=caption, token=token)
    except Exception:
        LOGGER.warning("Failed to send Telegram document chat_id=%s file=%s", chat_id, filepath, exc_info=True)


def _with_db(settings: Settings) -> sqlite3.Connection:
    connection = sqlite3.connect(settings.db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    connection.execute("PRAGMA journal_mode = WAL;")
    return connection


def _friendly_handler_error(chat_id: str) -> None:
    send_message(_get_bot_token(), chat_id, "The command could not be processed right now. Try again later.", parse_mode=None)


def _format_post_snippet(text: str | None, limit: int = 150) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _normalize_tag(raw_tag: str) -> str | None:
    return TAG_ALIASES.get(raw_tag.strip().lower())


def _resolve_post_reference(connection: sqlite3.Connection, raw_ref: str) -> sqlite3.Row | None:
    ref = raw_ref.strip()
    if ref.isdigit() and int(ref) > 0:
        return connection.execute(
            "SELECT id, channel_username, content FROM posts WHERE id = ? LIMIT 1",
            (int(ref),),
        ).fetchone()

    match = TELEGRAM_POST_URL_RE.match(ref)
    if not match:
        return None

    channel_username = f"@{match.group(1)}"
    message_id = int(match.group(2))
    return connection.execute(
        """
        SELECT p.id, p.channel_username, p.content
        FROM posts p
        INNER JOIN raw_posts r ON r.id = p.raw_post_id
        WHERE lower(r.channel_username) = lower(?) AND r.message_id = ?
        LIMIT 1
        """,
        (channel_username, message_id),
    ).fetchone()


def _extract_question_terms(question: str) -> list[str]:
    terms = []
    for raw_term in QUESTION_WORD_RE.findall(question.lower()):
        if len(raw_term) < 3:
            continue
        if raw_term not in terms:
            terms.append(raw_term)
    return terms[:8]


def _build_fts_query(question: str) -> str:
    terms = _extract_question_terms(question)
    if not terms:
        return ""
    return " OR ".join(f'"{term.replace(chr(34), " ").strip()}"' for term in terms if term.strip())


def _load_topics_summary(connection: sqlite3.Connection) -> str:
    rows = connection.execute(
        """
        SELECT label, description, post_count
        FROM topics
        ORDER BY post_count DESC, label ASC
        LIMIT 20
        """
    ).fetchall()
    if not rows:
        return "No topics yet."
    return "\n".join(
        f"- {row['label']} ({row['post_count']}): {row['description'] or 'no description'}" for row in rows
    )


def handle_start(chat_id: str, args: str, settings: Settings) -> None:
    del args, settings
    lines = ["Telegram Research Agent", "", "Available commands:"]
    for command, (_, description) in COMMAND_DOCS.items():
        lines.append(f"{command} — {description}")
    send_message(_get_bot_token(), chat_id, "\n".join(lines), parse_mode=None)


def handle_digest(chat_id: str, args: str, settings: Settings) -> None:
    del args
    week_label = _compute_week_label()

    with _with_db(settings) as connection:
        row = connection.execute(
            """
            SELECT content_md
            FROM digests
            WHERE week_label = ?
            """,
            (week_label,),
        ).fetchone()

        if row is None:
            row = connection.execute(
                """
                SELECT content_md
                FROM digests
                ORDER BY week_label DESC
                LIMIT 1
                """
            ).fetchone()

    if row is None or not row["content_md"]:
        send_message(
            _get_bot_token(),
            chat_id,
            "This week's brief is not ready yet. Run /run_digest.",
            parse_mode=None,
        )
        return

    try:
        send_text(chat_id=chat_id, text=row["content_md"], token=_get_bot_token(), parse_mode=None)
    except Exception:
        LOGGER.warning("Failed to send digest text chat_id=%s week=%s", chat_id, week_label, exc_info=True)
        _friendly_handler_error(chat_id)


def handle_topics(chat_id: str, args: str, settings: Settings) -> None:
    del args
    with _with_db(settings) as connection:
        rows = connection.execute(
            """
            SELECT id, label, description, post_count, last_seen
            FROM topics
            ORDER BY post_count DESC, label ASC
            """
        ).fetchall()

    if not rows:
        send_message(_get_bot_token(), chat_id, "No topics yet.", parse_mode=None)
        return

    lines = []
    for index, row in enumerate(rows, start=1):
        description = row["description"] or "no description"
        lines.append(f"{index}. {row['label']} ({row['post_count']} posts) — {description}")
    send_message(_get_bot_token(), chat_id, "\n".join(lines), parse_mode=None)


def handle_insight(chat_id: str, args: str, settings: Settings) -> None:
    del args
    result = generate_insight(settings.db_path, lookback_days=90).strip()
    if not result:
        send_message(_get_bot_token(), chat_id, "No active projects found. Sync or define projects first.", parse_mode=None)
        return
    send_message(_get_bot_token(), chat_id, result, parse_mode=None)


def handle_project(chat_id: str, args: str, settings: Settings) -> None:
    project_query = args.strip()
    if not project_query:
        send_message(_get_bot_token(), chat_id, "Usage: /project <partial-name>", parse_mode=None)
        return

    with _with_db(settings) as connection:
        projects = connection.execute(
            """
            SELECT DISTINCT
                p.id,
                p.name,
                p.description,
                p.keywords,
                p.last_commit_at
            FROM projects p
            LEFT JOIN post_project_links ppl ON p.id = ppl.project_id
            LEFT JOIN posts po ON ppl.post_id = po.id
            LEFT JOIN post_topics pt ON po.id = pt.post_id
            LEFT JOIN topics t ON pt.topic_id = t.id
            WHERE lower(p.name) LIKE lower('%' || ? || '%') AND p.active = 1
            ORDER BY p.name ASC
            LIMIT 5
            """,
            (project_query,),
        ).fetchall()

        if not projects:
            send_message(
                _get_bot_token(),
                chat_id,
                "Project not found. Use /project <partial-name> to search active projects.",
                parse_mode=None,
            )
            return

        sections = []
        for project in projects:
            topic_rows = connection.execute(
                """
                SELECT DISTINCT t.label
                FROM post_project_links ppl
                INNER JOIN posts po ON ppl.post_id = po.id
                LEFT JOIN post_topics pt ON po.id = pt.post_id
                LEFT JOIN topics t ON pt.topic_id = t.id
                WHERE ppl.project_id = ? AND t.label IS NOT NULL
                ORDER BY t.label ASC
                """,
                (project["id"],),
            ).fetchall()
            post_rows = connection.execute(
                """
                SELECT po.posted_at, po.channel_username, po.content
                FROM post_project_links ppl
                INNER JOIN posts po ON ppl.post_id = po.id
                WHERE ppl.project_id = ?
                ORDER BY ppl.relevance_score DESC, po.posted_at DESC
                LIMIT 3
                """,
                (project["id"],),
            ).fetchall()

            topics = ", ".join(row["label"] for row in topic_rows) or "no linked topics"
            last_commit = project["last_commit_at"] or "unknown"
            lines = [
                project["name"],
                f"Last commit: {last_commit}",
                f"Topics: {topics}",
            ]
            if project["description"]:
                lines.append(f"Description: {project['description']}")
            if project["keywords"]:
                lines.append(f"Keywords: {project['keywords']}")
            if post_rows:
                lines.append("Linked posts:")
                for row in post_rows:
                    lines.append(
                        f"- {row['posted_at']} @{row['channel_username']}: {_format_post_snippet(row['content'])}"
                    )
            else:
                lines.append("Linked posts: none")
            sections.append("\n".join(lines))

    send_message(_get_bot_token(), chat_id, "\n\n".join(sections), parse_mode=None)


def handle_ask(chat_id: str, args: str, settings: Settings) -> None:
    question = args.strip()
    if not question:
        send_message(_get_bot_token(), chat_id, "Usage: /ask <question>", parse_mode=None)
        return

    cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat().replace("+00:00", "Z")
    fts_query = _build_fts_query(question)

    with _with_db(settings) as connection:
        excerpts: list[str] = []
        if fts_query:
            rows = connection.execute(
                """
                SELECT posts.posted_at, posts.channel_username, posts.content
                FROM posts_fts
                INNER JOIN posts ON posts.id = posts_fts.rowid
                WHERE posts_fts MATCH ? AND posts.posted_at >= ?
                ORDER BY posts.posted_at DESC, posts.id DESC
                LIMIT 10
                """,
                (fts_query, cutoff_iso),
            ).fetchall()
            excerpts = [
                f"- {row['posted_at']} @{row['channel_username']}: {_format_post_snippet(row['content'], limit=220)}"
                for row in rows
            ]
        topics_summary = _load_topics_summary(connection)

    response_text = generate_answer(
        question=question,
        context={
            "topics_summary": topics_summary,
            "excerpts": excerpts,
        },
        settings=settings,
    )
    send_message(_get_bot_token(), chat_id, response_text, parse_mode=None)


def handle_costs(chat_id: str, args: str, settings: Settings) -> None:
    del args
    cutoff_30d = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat().replace("+00:00", "Z")

    with _with_db(settings) as connection:
        total_row = connection.execute(
            """
            SELECT
                COUNT(*) AS calls,
                SUM(input_tokens) AS total_input,
                SUM(output_tokens) AS total_output,
                SUM(cost_usd) AS total_cost,
                AVG(duration_ms) AS avg_ms
            FROM llm_usage
            """
        ).fetchone()
        category_rows = connection.execute(
            """
            SELECT
                category,
                COUNT(*) AS calls,
                SUM(cost_usd) AS cost,
                AVG(duration_ms) AS avg_ms
            FROM llm_usage
            WHERE called_at >= ?
            GROUP BY category
            ORDER BY cost DESC
            """,
            (cutoff_30d,),
        ).fetchall()
        month_rows = connection.execute(
            """
            SELECT
                substr(called_at, 1, 7) AS month,
                SUM(cost_usd) AS cost,
                COUNT(*) AS calls
            FROM llm_usage
            GROUP BY month
            ORDER BY month DESC
            LIMIT 8
            """
        ).fetchall()

    total_calls = int(total_row["calls"] or 0)
    total_cost = float(total_row["total_cost"] or 0.0)
    avg_ms = float(total_row["avg_ms"] or 0.0)

    lines = [
        "LLM Usage Statistics",
        "",
        "All time:",
        f"  Calls: {total_calls} | Cost: ${total_cost:.4f} | Avg: {avg_ms / 1000:.1f}s",
        "",
        "By category (last 30 days):",
    ]

    if category_rows:
        for row in category_rows:
            lines.append(
                f"  {row['category']:<16} {int(row['calls'] or 0)} calls  "
                f"${float(row['cost'] or 0.0):.4f}  avg {float(row['avg_ms'] or 0.0) / 1000:.1f}s"
            )
    else:
        lines.append("  No usage in the last 30 days.")

    lines.extend(["", "By month:"])
    if month_rows:
        for row in month_rows:
            lines.append(
                f"  {row['month']}  {int(row['calls'] or 0)} calls  ${float(row['cost'] or 0.0):.4f}"
            )
    else:
        lines.append("  No usage recorded yet.")

    send_message(_get_bot_token(), chat_id, "\n".join(lines), parse_mode=None)


def handle_study(chat_id: str, args: str, settings: Settings) -> None:
    force = any(token.lower() in {"refresh", "rebuild", "force"} for token in args.split())
    content_md = generate_study_plan(settings, force=force)
    send_message(_get_bot_token(), chat_id, content_md, parse_mode="Markdown", escape_markdown=False)


def handle_study_done(chat_id: str, args: str, settings: Settings) -> None:
    notes = args.strip() or None
    try:
        week_label = mark_study_complete(settings, notes=notes)
        message = f"Study plan marked as completed for {week_label}."
        if notes:
            message += f"\nNotes: {notes}"
        send_message(_get_bot_token(), chat_id, message, parse_mode=None)
    except Exception as exc:
        send_message(_get_bot_token(), chat_id, f"Failed to update study progress: {exc}", parse_mode=None)


def handle_run_digest(chat_id: str, args: str, settings: Settings) -> None:
    force_delivery = args.strip().lower() in {"force", "--force", "redeliver"}
    if force_delivery:
        summary = run_digest(settings, force_delivery=True)
    else:
        summary = run_digest(settings)
    summary_lines = [summary.output_path]
    if summary.json_path:
        summary_lines.append(summary.json_path)
    send_report_preview(
        chat_id=chat_id,
        title="Дайджест сгенерирован",
        summary_lines=summary_lines,
        week_label=summary.week_label,
        token=_get_bot_token(),
    )


def handle_status(chat_id: str, args: str, settings: Settings) -> None:
    del args
    with _with_db(settings) as connection:
        raw_posts_count = connection.execute("SELECT COUNT(*) FROM raw_posts").fetchone()[0]
        posts_count = connection.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
        topics_count = connection.execute("SELECT COUNT(*) FROM topics").fetchone()[0]
        projects_count = connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        last_ingestion = connection.execute("SELECT MAX(ingested_at) FROM raw_posts").fetchone()[0] or "never"
        last_digest = connection.execute("SELECT MAX(week_label) FROM digests").fetchone()[0] or "none"

    channels_path = PROJECT_ROOT / "src" / "config" / "channels.yaml"
    active_channels = 0
    if channels_path.exists():
        for line in channels_path.read_text(encoding="utf-8").splitlines():
            if line.strip() == "active: true":
                active_channels += 1

    message = (
        f"Status\n"
        f"raw_posts: {raw_posts_count}\n"
        f"posts: {posts_count}\n"
        f"topics: {topics_count}\n"
        f"projects: {projects_count}\n"
        f"last_ingestion: {last_ingestion}\n"
        f"last_digest: {last_digest}\n"
        f"active_channels: {active_channels}"
    )
    send_message(_get_bot_token(), chat_id, message, parse_mode=None)


def _handle_mark_feedback(chat_id: str, args: str, settings: Settings, feedback_value: str) -> None:
    post_ref = args.strip().split()[0] if args.strip() else ""
    if not post_ref:
        send_message(
            _get_bot_token(),
            chat_id,
            f"Usage: /mark_{'useful' if feedback_value == 'acted_on' else 'skipped'} <post_id|link>",
            parse_mode=None,
        )
        return
    try:
        with _with_db(settings) as connection:
            row = _resolve_post_reference(connection, post_ref)
            if row is None:
                send_message(
                    _get_bot_token(),
                    chat_id,
                    f"Post not found: {post_ref}",
                    parse_mode=None,
                )
                return
            post_id = int(row["id"])
            record_feedback(connection, post_id, feedback_value)
        send_message(
            _get_bot_token(),
            chat_id,
            f"Feedback recorded: {feedback_value} for post {post_id}",
            parse_mode=None,
        )
    except Exception as exc:
        send_message(_get_bot_token(), chat_id, f"Failed to record feedback: {exc}", parse_mode=None)


def _handle_post_tag(chat_id: str, args: str, settings: Settings, tag_value: str | None = None) -> None:
    parts = args.strip().split(maxsplit=2)
    if tag_value is None:
        if len(parts) < 2:
            send_message(
                _get_bot_token(),
                chat_id,
                "Usage: /tag <post_id|link> <strong|interesting|try|funny|low|later>",
                parse_mode=None,
            )
            return
        post_ref, raw_tag = parts[0], parts[1]
        note = parts[2] if len(parts) > 2 else None
        normalized_tag = _normalize_tag(raw_tag)
    else:
        if not parts:
            send_message(
                _get_bot_token(),
                chat_id,
                f"Usage: /mark_{tag_value} <post_id|link>",
                parse_mode=None,
            )
            return
        post_ref = parts[0]
        note = parts[1] if len(parts) > 1 else None
        normalized_tag = _normalize_tag(tag_value)

    if not post_ref or normalized_tag is None:
        send_message(
            _get_bot_token(),
            chat_id,
            "Usage: /tag <post_id|link> <strong|interesting|try|funny|low|later>",
            parse_mode=None,
        )
        return
    try:
        with _with_db(settings) as connection:
            row = _resolve_post_reference(connection, post_ref)
            if row is None:
                send_message(_get_bot_token(), chat_id, f"Post not found: {post_ref}", parse_mode=None)
                return
            post_id = int(row["id"])
            record_post_tag(connection, post_id, normalized_tag, note)
            snippet = _format_post_snippet(row["content"], limit=100)
        send_message(
            _get_bot_token(),
            chat_id,
            f"Tag saved: {normalized_tag} for post {post_id}\n@{row['channel_username']}: {snippet}",
            parse_mode=None,
        )
    except Exception as exc:
        send_message(_get_bot_token(), chat_id, f"Failed to save tag: {exc}", parse_mode=None)


def handle_mark_useful(chat_id: str, args: str, settings: Settings) -> None:
    _handle_mark_feedback(chat_id, args, settings, "acted_on")


def handle_mark_skipped(chat_id: str, args: str, settings: Settings) -> None:
    _handle_mark_feedback(chat_id, args, settings, "skipped")


def handle_tag(chat_id: str, args: str, settings: Settings) -> None:
    _handle_post_tag(chat_id, args, settings)


def handle_mark_strong(chat_id: str, args: str, settings: Settings) -> None:
    _handle_post_tag(chat_id, args, settings, "strong")


def handle_mark_interesting(chat_id: str, args: str, settings: Settings) -> None:
    _handle_post_tag(chat_id, args, settings, "interesting")


def handle_mark_try(chat_id: str, args: str, settings: Settings) -> None:
    _handle_post_tag(chat_id, args, settings, "try")


def handle_mark_funny(chat_id: str, args: str, settings: Settings) -> None:
    _handle_post_tag(chat_id, args, settings, "funny")


def handle_mark_low(chat_id: str, args: str, settings: Settings) -> None:
    _handle_post_tag(chat_id, args, settings, "low")


def handle_mark_later(chat_id: str, args: str, settings: Settings) -> None:
    _handle_post_tag(chat_id, args, settings, "later")


HANDLERS: dict[str, Callable[[str, str, Settings], None]] = {
    "/start": handle_start,
    "/digest": handle_digest,
    "/topics": handle_topics,
    "/insight": handle_insight,
    "/project": handle_project,
    "/ask": handle_ask,
    "/study": handle_study,
    "/study_done": handle_study_done,
    "/costs": handle_costs,
    "/run_digest": handle_run_digest,
    "/status": handle_status,
    "/mark_useful": handle_mark_useful,
    "/mark_skipped": handle_mark_skipped,
    "/tag": handle_tag,
    "/mark_strong": handle_mark_strong,
    "/mark_interesting": handle_mark_interesting,
    "/mark_try": handle_mark_try,
    "/mark_funny": handle_mark_funny,
    "/mark_low": handle_mark_low,
    "/mark_later": handle_mark_later,
}


def dispatch_command(chat_id: str, text: str, settings: Settings) -> None:
    command, _, args = text.strip().partition(" ")
    command = command.split("@", maxsplit=1)[0]
    handler = HANDLERS.get(command)
    if handler is None:
        send_message(
            _get_bot_token(),
            chat_id,
            "Unknown command. Use /start to see the available commands.",
            parse_mode=None,
        )
        return

    try:
        handler(chat_id, args, settings)
    except sqlite3.OperationalError:
        LOGGER.warning("Bot handler database error command=%s", command, exc_info=True)
        _friendly_handler_error(chat_id)
    except error.HTTPError:
        LOGGER.warning("Bot handler HTTP error command=%s", command, exc_info=True)
        _friendly_handler_error(chat_id)
    except Exception:
        LOGGER.exception("Bot handler failed command=%s", command)
        _friendly_handler_error(chat_id)
