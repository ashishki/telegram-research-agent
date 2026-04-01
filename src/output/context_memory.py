import json
import logging
import sqlite3
from datetime import datetime, timezone


LOGGER = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def refresh_channel_memory(connection: sqlite3.Connection) -> None:
    try:
        rows = connection.execute(
            """
            SELECT
                p.channel_username,
                SUM(CASE WHEN upt.tag IN ('strong', 'try_in_project', 'interesting') THEN 1 ELSE 0 END) AS positive_tags,
                SUM(CASE WHEN upt.tag = 'low_signal' THEN 1 ELSE 0 END) AS negative_tags,
                SUM(CASE WHEN upt.tag = 'strong' THEN 1 ELSE 0 END) AS strong_tags,
                SUM(CASE WHEN upt.tag = 'try_in_project' THEN 1 ELSE 0 END) AS try_tags,
                SUM(CASE WHEN upt.tag = 'interesting' THEN 1 ELSE 0 END) AS interesting_tags,
                SUM(CASE WHEN upt.tag = 'funny' THEN 1 ELSE 0 END) AS funny_tags,
                SUM(CASE WHEN upt.tag = 'low_signal' THEN 1 ELSE 0 END) AS low_signal_tags,
                SUM(CASE WHEN upt.tag = 'read_later' THEN 1 ELSE 0 END) AS read_later_tags
            FROM user_post_tags upt
            INNER JOIN posts p ON p.id = upt.post_id
            GROUP BY p.channel_username
            """
        ).fetchall()
    except sqlite3.Error:
        LOGGER.warning("Failed to refresh channel memory", exc_info=True)
        return
    now = _utc_now_iso()
    connection.execute("BEGIN")
    for row in rows:
        strong_tags = int(row["strong_tags"] or 0)
        try_tags = int(row["try_tags"] or 0)
        interesting_tags = int(row["interesting_tags"] or 0)
        funny_tags = int(row["funny_tags"] or 0)
        low_signal_tags = int(row["low_signal_tags"] or 0)
        read_later_tags = int(row["read_later_tags"] or 0)
        positive_tags = int(row["positive_tags"] or 0)
        negative_tags = int(row["negative_tags"] or 0)
        summary_parts: list[str] = []
        if strong_tags:
            summary_parts.append(f"strong source for high-value signals ({strong_tags})")
        if try_tags:
            summary_parts.append(f"often produces ideas worth trying ({try_tags})")
        if interesting_tags:
            summary_parts.append(f"frequently worth tracking ({interesting_tags})")
        if funny_tags:
            summary_parts.append(f"occasionally useful as cultural context ({funny_tags})")
        if read_later_tags:
            summary_parts.append(f"contains items worth revisiting later ({read_later_tags})")
        if low_signal_tags:
            summary_parts.append(f"also produces recurring noise ({low_signal_tags})")
        summary = "; ".join(summary_parts) or "No clear memory yet."
        connection.execute(
            """
            INSERT INTO channel_memory (
                channel_username,
                summary,
                positive_tags,
                negative_tags,
                strong_tags,
                try_tags,
                interesting_tags,
                funny_tags,
                low_signal_tags,
                read_later_tags,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(channel_username) DO UPDATE SET
                summary = excluded.summary,
                positive_tags = excluded.positive_tags,
                negative_tags = excluded.negative_tags,
                strong_tags = excluded.strong_tags,
                try_tags = excluded.try_tags,
                interesting_tags = excluded.interesting_tags,
                funny_tags = excluded.funny_tags,
                low_signal_tags = excluded.low_signal_tags,
                read_later_tags = excluded.read_later_tags,
                updated_at = excluded.updated_at
            """,
            (
                str(row["channel_username"] or ""),
                summary,
                positive_tags,
                negative_tags,
                strong_tags,
                try_tags,
                interesting_tags,
                funny_tags,
                low_signal_tags,
                read_later_tags,
                now,
            ),
        )
    connection.commit()


def load_channel_memory(connection: sqlite3.Connection, channels: list[str]) -> dict[str, dict]:
    if not channels:
        return {}
    unique_channels = list(dict.fromkeys(channel for channel in channels if channel))
    placeholders = ",".join("?" for _ in unique_channels)
    try:
        rows = connection.execute(
            f"""
            SELECT channel_username, summary, positive_tags, negative_tags, strong_tags, try_tags,
                   interesting_tags, funny_tags, low_signal_tags, read_later_tags, updated_at
            FROM channel_memory
            WHERE channel_username IN ({placeholders})
            """,
            unique_channels,
        ).fetchall()
    except sqlite3.Error:
        LOGGER.warning("Failed to load channel memory", exc_info=True)
        return {}
    return {
        str(row["channel_username"]): {
            "summary": str(row["summary"] or ""),
            "positive_tags": int(row["positive_tags"] or 0),
            "negative_tags": int(row["negative_tags"] or 0),
            "strong_tags": int(row["strong_tags"] or 0),
            "try_tags": int(row["try_tags"] or 0),
            "interesting_tags": int(row["interesting_tags"] or 0),
            "funny_tags": int(row["funny_tags"] or 0),
            "low_signal_tags": int(row["low_signal_tags"] or 0),
            "read_later_tags": int(row["read_later_tags"] or 0),
            "updated_at": str(row["updated_at"] or ""),
        }
        for row in rows
    }


def refresh_project_context_snapshot(
    connection: sqlite3.Connection,
    project_id: int,
    project_name: str,
    description: str,
    focus: str,
    keywords: list[str],
    github_repo: str,
    last_commit_at: str,
    recent_changes: list[str] | None = None,
) -> None:
    recent_changes = recent_changes or []
    linked_posts = connection.execute(
        """
        SELECT COUNT(*) AS linked_count, MAX(po.posted_at) AS last_posted_at
        FROM post_project_links ppl
        INNER JOIN posts po ON po.id = ppl.post_id
        WHERE ppl.project_id = ?
        """,
        (project_id,),
    ).fetchone()
    linked_count = int(linked_posts["linked_count"] or 0) if linked_posts is not None else 0
    last_linked_post = str(linked_posts["last_posted_at"] or "") if linked_posts is not None else ""
    summary = (
        f"{project_name}: {description.strip()} "
        f"Focus: {focus.strip() or 'not specified'}. "
        f"Keywords: {', '.join(keywords) if keywords else 'none'}. "
        f"Linked Telegram signals: {linked_count}."
    ).strip()
    open_questions = ""
    if not keywords:
        open_questions = "Keywords are missing or weak; project matching may be too shallow."
    elif linked_count == 0:
        open_questions = "No linked Telegram signals yet; project relevance likely needs stronger context."
    context_json = json.dumps(
        {
            "description": description,
            "focus": focus,
            "keywords": keywords,
            "github_repo": github_repo,
            "last_commit_at": last_commit_at,
            "last_linked_post": last_linked_post,
            "recent_changes": recent_changes,
            "linked_telegram_signals": linked_count,
        },
        ensure_ascii=False,
    )
    connection.execute(
        """
        INSERT INTO project_context_snapshots (
            project_id,
            project_name,
            github_repo,
            source_commit_at,
            summary,
            open_questions,
            recent_changes,
            context_json,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(project_id) DO UPDATE SET
            project_name = excluded.project_name,
            github_repo = excluded.github_repo,
            source_commit_at = excluded.source_commit_at,
            summary = excluded.summary,
            open_questions = excluded.open_questions,
            recent_changes = excluded.recent_changes,
            context_json = excluded.context_json,
            updated_at = excluded.updated_at
        """,
        (
            project_id,
            project_name,
            github_repo,
            last_commit_at,
            summary,
            open_questions,
            "\n".join(recent_changes[:8]),
            context_json,
            _utc_now_iso(),
        ),
    )


def load_project_context(connection: sqlite3.Connection, project_names: list[str] | None = None) -> list[dict]:
    params: tuple = ()
    sql = """
        SELECT project_id, project_name, github_repo, source_commit_at, summary, open_questions, recent_changes, context_json, updated_at
        FROM project_context_snapshots
    """
    if project_names:
        names = [name for name in project_names if name]
        if names:
            placeholders = ",".join("?" for _ in names)
            sql += f" WHERE project_name IN ({placeholders})"
            params = tuple(names)
    sql += " ORDER BY project_name ASC"
    try:
        rows = connection.execute(sql, params).fetchall()
    except sqlite3.Error:
        LOGGER.warning("Failed to load project context snapshots", exc_info=True)
        return []
    snapshots: list[dict] = []
    for row in rows:
        try:
            context = json.loads(row["context_json"] or "{}")
        except json.JSONDecodeError:
            context = {}
        snapshots.append(
            {
                "project_id": int(row["project_id"]),
                "project_name": str(row["project_name"] or ""),
                "github_repo": str(row["github_repo"] or ""),
                "source_commit_at": str(row["source_commit_at"] or ""),
                "summary": str(row["summary"] or ""),
                "open_questions": str(row["open_questions"] or ""),
                "recent_changes": str(row["recent_changes"] or ""),
                "context": context if isinstance(context, dict) else {},
                "updated_at": str(row["updated_at"] or ""),
            }
        )
    return snapshots
