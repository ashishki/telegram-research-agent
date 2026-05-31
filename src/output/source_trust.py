import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any


def _cutoff_iso(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=max(1, int(days or 30)))).isoformat().replace("+00:00", "Z")


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        LIMIT 1
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _column_exists(connection: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    if not _table_exists(connection, table_name):
        return False
    return any(row[1] == column_name for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall())


def _channel_key(value: Any) -> str:
    return str(value or "").strip() or "unknown"


def _add_reason(summary: dict[str, Any], reason: str, count: int) -> None:
    if count <= 0:
        return
    summary["reason_counts"][reason] += int(count)


def explain_source_downrank(
    connection: sqlite3.Connection,
    *,
    channel: str | None = None,
    days: int = 30,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Explain source down-ranking from observed local behavior only."""
    cutoff = _cutoff_iso(days)
    summaries: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "channel": "",
            "post_count": 0,
            "reason_counts": defaultdict(int),
        }
    )

    if _table_exists(connection, "posts") and _table_exists(connection, "raw_posts"):
        channel_clause = "AND lower(p.channel_username) = lower(?)" if channel else ""
        params: tuple[Any, ...] = (cutoff, channel) if channel else (cutoff,)
        rows = connection.execute(
            f"""
            SELECT p.channel_username,
                   COUNT(*) AS post_count,
                   SUM(CASE WHEN p.bucket = 'noise' THEN 1 ELSE 0 END) AS noise_count,
                   SUM(CASE WHEN r.message_url IS NULL OR trim(r.message_url) = '' THEN 1 ELSE 0 END) AS missing_link_count
            FROM posts p
            LEFT JOIN raw_posts r ON r.id = p.raw_post_id
            WHERE p.posted_at >= ?
              {channel_clause}
            GROUP BY p.channel_username
            """,
            params,
        ).fetchall()
        for row in rows:
            channel_name = _channel_key(row["channel_username"] if isinstance(row, sqlite3.Row) else row[0])
            summary = summaries[channel_name]
            summary["channel"] = channel_name
            summary["post_count"] += int(row["post_count"] if isinstance(row, sqlite3.Row) else row[1] or 0)
            _add_reason(summary, "many_posts_scored_noise", int(row["noise_count"] if isinstance(row, sqlite3.Row) else row[2] or 0))
            _add_reason(summary, "missing_source_links", int(row["missing_link_count"] if isinstance(row, sqlite3.Row) else row[3] or 0))

    if _table_exists(connection, "user_post_tags") and _table_exists(connection, "posts"):
        channel_clause = "AND lower(p.channel_username) = lower(?)" if channel else ""
        params = (cutoff, channel) if channel else (cutoff,)
        rows = connection.execute(
            f"""
            SELECT p.channel_username, t.tag, COUNT(*) AS count
            FROM user_post_tags t
            INNER JOIN posts p ON p.id = t.post_id
            WHERE t.recorded_at >= ?
              {channel_clause}
            GROUP BY p.channel_username, t.tag
            """,
            params,
        ).fetchall()
        for row in rows:
            channel_name = _channel_key(row["channel_username"] if isinstance(row, sqlite3.Row) else row[0])
            tag = row["tag"] if isinstance(row, sqlite3.Row) else row[1]
            count = int(row["count"] if isinstance(row, sqlite3.Row) else row[2] or 0)
            summary = summaries[channel_name]
            summary["channel"] = channel_name
            if tag == "low_signal":
                _add_reason(summary, "operator_low_signal_tags", count)

    if _table_exists(connection, "signal_feedback") and _table_exists(connection, "posts"):
        channel_clause = "AND lower(p.channel_username) = lower(?)" if channel else ""
        params = (cutoff, channel) if channel else (cutoff,)
        rows = connection.execute(
            f"""
            SELECT p.channel_username, f.feedback, COUNT(*) AS count
            FROM signal_feedback f
            INNER JOIN posts p ON p.id = f.post_id
            WHERE f.recorded_at >= ?
              {channel_clause}
            GROUP BY p.channel_username, f.feedback
            """,
            params,
        ).fetchall()
        for row in rows:
            channel_name = _channel_key(row["channel_username"] if isinstance(row, sqlite3.Row) else row[0])
            feedback = row["feedback"] if isinstance(row, sqlite3.Row) else row[1]
            count = int(row["count"] if isinstance(row, sqlite3.Row) else row[2] or 0)
            summary = summaries[channel_name]
            summary["channel"] = channel_name
            if feedback == "skipped":
                _add_reason(summary, "operator_skipped_feedback", count)

    if _table_exists(connection, "source_observations"):
        channel_clause = "AND lower(channel_username) = lower(?)" if channel else ""
        params = (channel,) if channel else ()
        rows = connection.execute(
            f"""
            SELECT channel_username,
                   SUM(low_signal_count) AS low_signal_count,
                   SUM(rejected_count) AS rejected_count,
                   SUM(skipped_count) AS skipped_count
            FROM source_observations
            WHERE 1 = 1
              {channel_clause}
            GROUP BY channel_username
            """,
            params,
        ).fetchall()
        for row in rows:
            channel_name = _channel_key(row["channel_username"] if isinstance(row, sqlite3.Row) else row[0])
            summary = summaries[channel_name]
            summary["channel"] = channel_name
            _add_reason(summary, "source_observation_low_signal", int(row["low_signal_count"] if isinstance(row, sqlite3.Row) else row[1] or 0))
            _add_reason(summary, "source_observation_rejected", int(row["rejected_count"] if isinstance(row, sqlite3.Row) else row[2] or 0))
            _add_reason(summary, "source_observation_skipped", int(row["skipped_count"] if isinstance(row, sqlite3.Row) else row[3] or 0))

    if _column_exists(connection, "posts", "project_relevance_score"):
        channel_clause = "AND lower(channel_username) = lower(?)" if channel else ""
        params = (cutoff, channel) if channel else (cutoff,)
        rows = connection.execute(
            f"""
            SELECT channel_username, COUNT(*) AS count
            FROM posts
            WHERE posted_at >= ?
              AND COALESCE(project_relevance_score, 0) <= 0
              {channel_clause}
            GROUP BY channel_username
            """,
            params,
        ).fetchall()
        for row in rows:
            channel_name = _channel_key(row["channel_username"] if isinstance(row, sqlite3.Row) else row[0])
            summary = summaries[channel_name]
            summary["channel"] = channel_name
            _add_reason(summary, "low_project_relevance", int(row["count"] if isinstance(row, sqlite3.Row) else row[1] or 0))

    results = []
    for summary in summaries.values():
        reason_counts = dict(summary["reason_counts"])
        if not reason_counts:
            continue
        total = sum(reason_counts.values())
        results.append(
            {
                "channel": summary["channel"],
                "post_count": int(summary["post_count"]),
                "reason_counts": reason_counts,
                "total_negative_observations": total,
            }
        )
    results.sort(key=lambda item: (-int(item["total_negative_observations"]), str(item["channel"])))
    return results[: max(1, int(limit or 10))]


def format_source_downrank_explanations(explanations: list[dict[str, Any]]) -> str:
    if not explanations:
        return "No source down-rank explanations found for the given scope.\n"
    lines: list[str] = []
    for item in explanations:
        lines.append(
            f"Source {item['channel']} negative_observations={item['total_negative_observations']} "
            f"posts={item['post_count']}"
        )
        for reason, count in sorted(item["reason_counts"].items(), key=lambda pair: (-pair[1], pair[0])):
            lines.append(f"  {reason}: {count}")
    return "\n".join(lines) + "\n"
