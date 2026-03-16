import json
import logging
import os
import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from urllib import error, parse, request

from config.settings import PROJECT_ROOT, Settings
from llm.client import LLMClient
from output.generate_digest import _compute_week_label, run_digest
from output.generate_insight import generate_insight
from output.generate_recommendations import generate_recommendations


LOGGER = logging.getLogger(__name__)
BOT_API_BASE = "https://api.telegram.org"
MESSAGE_CHUNK_SIZE = 4000
QUESTION_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)
MARKDOWN_V2_SPECIAL_CHARS = r"_*[]()~`>#+-=|{}.!"
COMMAND_DOCS: dict[str, tuple[str, str]] = {
    "/digest": ("handle_digest", "Показать дайджест за текущую неделю"),
    "/topics": ("handle_topics", "Список тем и их объём"),
    "/insight": ("handle_insight", "Ретроспективные инсайты по активным проектам"),
    "/project <имя>": ("handle_project", "Найти проект по части имени"),
    "/ask <вопрос>": ("handle_ask", "Ответ по данным Telegram за последние 7 дней"),
    "/run_digest": ("handle_run_digest", "Сгенерировать новый дайджест и рекомендации"),
    "/status": ("handle_status", "Краткий статус базы и пайплайна"),
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


def _chunk_text(text: str, chunk_size: int = MESSAGE_CHUNK_SIZE) -> list[str]:
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


def _telegram_request(url: str, data: bytes | None = None, headers: dict[str, str] | None = None) -> dict:
    http_request = request.Request(url, data=data, headers=headers or {}, method="POST" if data is not None else "GET")
    with request.urlopen(http_request, timeout=60) as response:
        payload = response.read().decode("utf-8")
    decoded = json.loads(payload)
    if not decoded.get("ok"):
        raise RuntimeError(f"Telegram API returned error: {decoded!r}")
    return decoded


def send_message(
    token: str,
    chat_id: str,
    text: str,
    parse_mode: str | None = "MarkdownV2",
    escape_markdown: bool = True,
) -> None:
    if not token:
        LOGGER.warning("Telegram send skipped because TELEGRAM_BOT_TOKEN is not set")
        return

    for chunk in _chunk_text(text):
        payload = {
            "chat_id": chat_id,
            "text": _escape_markdown_v2(chunk) if parse_mode == "MarkdownV2" and escape_markdown else chunk,
            "disable_web_page_preview": "true",
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        data = parse.urlencode(payload).encode("utf-8")
        url = f"{BOT_API_BASE}/bot{token}/sendMessage"
        try:
            _telegram_request(
                url=url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except Exception:
            LOGGER.warning("Failed to send Telegram message to chat_id=%s", chat_id, exc_info=True)


def send_file(token: str, chat_id: str, filepath: str, caption: str = "") -> None:
    if not token:
        LOGGER.warning("Telegram file send skipped because TELEGRAM_BOT_TOKEN is not set")
        return

    path = Path(filepath)
    if not path.exists():
        LOGGER.warning("Telegram file send skipped because file does not exist path=%s", path)
        return

    boundary = f"----codex-{uuid.uuid4().hex}"
    body = bytearray()

    def add_field(name: str, value: str) -> None:
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        body.extend(value.encode("utf-8"))
        body.extend(b"\r\n")

    add_field("chat_id", chat_id)
    if caption:
        add_field("caption", caption)

    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(
        (
            f'Content-Disposition: form-data; name="document"; filename="{path.name}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode("utf-8")
    )
    body.extend(path.read_bytes())
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))

    url = f"{BOT_API_BASE}/bot{token}/sendDocument"
    try:
        _telegram_request(
            url=url,
            data=bytes(body),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
    except Exception:
        LOGGER.warning("Failed to send Telegram document chat_id=%s file=%s", chat_id, path, exc_info=True)


def _with_db(settings: Settings) -> sqlite3.Connection:
    connection = sqlite3.connect(settings.db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    connection.execute("PRAGMA journal_mode = WAL;")
    return connection


def _friendly_handler_error(chat_id: str) -> None:
    send_message(_get_bot_token(), chat_id, "Не получилось обработать команду. Попробуй ещё раз позже.", parse_mode=None)


def _format_post_snippet(text: str | None, limit: int = 150) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


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
        return "Тем пока нет."
    return "\n".join(
        f"- {row['label']} ({row['post_count']}): {row['description'] or 'без описания'}" for row in rows
    )


def handle_start(chat_id: str, args: str, settings: Settings) -> None:
    del args, settings
    lines = ["Telegram Research Agent bot.", "", "Доступные команды:"]
    for command, (_, description) in COMMAND_DOCS.items():
        lines.append(f"{command} — {description}")
    send_message(_get_bot_token(), chat_id, "\n".join(lines), parse_mode=None)


def handle_digest(chat_id: str, args: str, settings: Settings) -> None:
    del args
    week_label = _compute_week_label()
    digest_path = PROJECT_ROOT / "data" / "output" / "digests" / f"{week_label}.md"
    if not digest_path.exists():
        send_message(
            _get_bot_token(),
            chat_id,
            "Дайджест за текущую неделю ещё не сгенерирован. Попробуй /run_digest",
            parse_mode=None,
        )
        return

    send_message(_get_bot_token(), chat_id, digest_path.read_text(encoding="utf-8"), parse_mode="Markdown", escape_markdown=False)


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
        send_message(_get_bot_token(), chat_id, "Тем пока нет.", parse_mode=None)
        return

    lines = []
    for index, row in enumerate(rows, start=1):
        description = row["description"] or "без описания"
        lines.append(f"{index}. {row['label']} ({row['post_count']} постов) — {description}")
    send_message(_get_bot_token(), chat_id, "\n".join(lines), parse_mode=None)


def handle_insight(chat_id: str, args: str, settings: Settings) -> None:
    del args
    result = generate_insight(settings.db_path, lookback_days=90).strip()
    if not result:
        send_message(_get_bot_token(), chat_id, "Активных проектов нет. Добавь проекты через GitHub sync.", parse_mode=None)
        return
    send_message(_get_bot_token(), chat_id, result, parse_mode=None)


def handle_project(chat_id: str, args: str, settings: Settings) -> None:
    project_query = args.strip()
    if not project_query:
        send_message(_get_bot_token(), chat_id, "Укажи часть имени: /project <часть имени>", parse_mode=None)
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
                "Проект не найден. Используй /topics чтобы посмотреть темы, /project <часть имени> для поиска.",
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

            topics = ", ".join(row["label"] for row in topic_rows) or "нет связанных тем"
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
        send_message(_get_bot_token(), chat_id, "Задай вопрос: /ask <вопрос>", parse_mode=None)
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

    context_block = "\n".join(excerpts) if excerpts else "Подходящих постов за последние 7 дней не найдено."
    prompt = (
        f"Question:\n{question}\n\n"
        f"Topics:\n{topics_summary}\n\n"
        f"Relevant Telegram excerpts from the last 7 days:\n{context_block}"
    )
    system = (
        "You are a research assistant. Answer based only on the provided Telegram channel data context. "
        "Be concise (max 300 words). Answer in the same language as the question."
    )

    response_text = LLMClient.complete(prompt=prompt, system=system, max_tokens=600).strip()
    if not response_text:
        response_text = "Не нашёл достаточно данных, чтобы ответить по последним постам."
    send_message(_get_bot_token(), chat_id, response_text, parse_mode=None)


def handle_run_digest(chat_id: str, args: str, settings: Settings) -> None:
    del args
    summary = run_digest(settings)
    generate_recommendations(settings)
    send_message(
        _get_bot_token(),
        chat_id,
        f"Дайджест сгенерирован: {summary['week_label']}\n{summary['output_path']}",
        parse_mode=None,
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


HANDLERS: dict[str, Callable[[str, str, Settings], None]] = {
    "/start": handle_start,
    "/digest": handle_digest,
    "/topics": handle_topics,
    "/insight": handle_insight,
    "/project": handle_project,
    "/ask": handle_ask,
    "/run_digest": handle_run_digest,
    "/status": handle_status,
}


def dispatch_command(chat_id: str, text: str, settings: Settings) -> None:
    command, _, args = text.strip().partition(" ")
    command = command.split("@", maxsplit=1)[0]
    handler = HANDLERS.get(command)
    if handler is None:
        send_message(
            _get_bot_token(),
            chat_id,
            "Неизвестная команда. Используй /start чтобы посмотреть доступные команды.",
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
