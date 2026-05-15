import json
import logging
import re
import sqlite3
from datetime import date, datetime, timezone
from typing import Any

from config.settings import Settings
from output.context_memory import _find_project_config, _project_is_curated
from output.project_relevance import _keyword_matches_content, _tokenize


LOGGER = logging.getLogger(__name__)
DEFAULT_TOPIC_LIMIT = 10


def _current_week_label() -> str:
    year, week, _ = datetime.now(timezone.utc).isocalendar()
    return f"{year}-W{week:02d}"


def _week_start_iso(week_label: str) -> str:
    year_str, week_str = week_label.split("-W", maxsplit=1)
    week_start = date.fromisocalendar(int(year_str), int(week_str), 1)
    return datetime(
        week_start.year,
        week_start.month,
        week_start.day,
        tzinfo=timezone.utc,
    ).isoformat().replace("+00:00", "Z")


def _parse_keywords(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        decoded = value
    if isinstance(decoded, list):
        return [str(item).strip() for item in decoded if str(item).strip()]
    if isinstance(decoded, str):
        return [part.strip() for part in decoded.split(",") if part.strip()]
    return []


def _project_keywords(row: sqlite3.Row, config: dict[str, Any]) -> list[str]:
    config_keywords = config.get("keywords")
    if isinstance(config_keywords, list) and config_keywords:
        return [str(item).strip() for item in config_keywords if str(item).strip()]
    return _parse_keywords(row["keywords"])


def _project_exclude_keywords(config: dict[str, Any]) -> list[str]:
    values = config.get("exclude_keywords")
    if not isinstance(values, list):
        return []
    return [str(item).strip() for item in values if str(item).strip()]


def _load_active_projects(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    rows = connection.execute(
        """
        SELECT id, name, github_repo, description, keywords
        FROM projects
        WHERE active = 1
        ORDER BY name ASC
        """
    ).fetchall()
    return [
        row
        for row in rows
        if _project_is_curated(str(row["name"] or ""), str(row["github_repo"] or ""))
    ]


def _load_digest_topics(
    connection: sqlite3.Connection,
    week_label: str,
    limit: int,
) -> list[dict[str, Any]]:
    row = connection.execute(
        """
        SELECT content_json
        FROM digests
        WHERE week_label = ?
        """,
        (week_label,),
    ).fetchone()
    if row is None or not row["content_json"]:
        return []

    try:
        payload = json.loads(row["content_json"])
    except (TypeError, ValueError):
        LOGGER.warning("Failed to parse digest content_json for week=%s", week_label, exc_info=True)
        return []

    topics: list[dict[str, Any]] = []
    for item in payload.get("key_findings") or []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("title") or "").strip()
        if not label:
            continue
        topics.append(
            {
                "topic_id": None,
                "label": label,
                "description": str(item.get("body") or ""),
                "post_count": _first_int(str(item.get("body") or "")),
            }
        )
        if len(topics) >= limit:
            break
    return topics


def _load_recent_topics(
    connection: sqlite3.Connection,
    week_start_iso: str,
    limit: int,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT
            t.id AS topic_id,
            t.label,
            COALESCE(t.description, '') AS description,
            COUNT(DISTINCT p.id) AS post_count,
            SUM(CASE WHEN p.bucket IN ('strong', 'watch') THEN 1 ELSE 0 END) AS signal_post_count
        FROM topics t
        INNER JOIN post_topics pt ON pt.topic_id = t.id
        INNER JOIN posts p ON p.id = pt.post_id
        WHERE p.posted_at >= ?
        GROUP BY t.id, t.label, t.description
        ORDER BY signal_post_count DESC, post_count DESC, t.label ASC
        LIMIT ?
        """,
        (week_start_iso, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def _first_int(text: str) -> int:
    match = re.search(r"\d+", text or "")
    return int(match.group(0)) if match else 0


def _topic_id_for_label(connection: sqlite3.Connection, label: str) -> int | None:
    row = connection.execute(
        """
        SELECT id
        FROM topics
        WHERE label = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (label,),
    ).fetchone()
    if row is None:
        return None
    return int(row["id"])


def _keyword_hits(text: str, keywords: list[str]) -> list[str]:
    content_lower = (text or "").lower()
    tokens = _tokenize(text or "")
    hits: list[str] = []
    seen: set[str] = set()
    for keyword in keywords:
        matched, terms = _keyword_matches_content(keyword, content_lower, tokens)
        if not matched:
            continue
        for term in terms or [keyword.lower()]:
            if term not in seen:
                hits.append(term)
                seen.add(term)
    return hits


def _post_match_stats(
    connection: sqlite3.Connection,
    *,
    topic_id: int | None,
    project_id: int,
    keywords: list[str],
    week_start_iso: str,
) -> dict[str, Any]:
    if topic_id is None:
        return {"post_keyword_match_count": 0, "linked_post_count": 0, "sample_post_ids": []}

    rows = connection.execute(
        """
        SELECT
            p.id,
            p.content,
            CASE WHEN ppl.post_id IS NULL THEN 0 ELSE 1 END AS is_linked
        FROM post_topics pt
        INNER JOIN posts p ON p.id = pt.post_id
        LEFT JOIN post_project_links ppl
            ON ppl.post_id = p.id AND ppl.project_id = ?
        WHERE pt.topic_id = ?
          AND p.posted_at >= ?
        ORDER BY p.user_adjusted_score DESC, p.signal_score DESC, p.posted_at DESC
        LIMIT 50
        """,
        (project_id, topic_id, week_start_iso),
    ).fetchall()

    post_keyword_match_count = 0
    linked_post_count = 0
    sample_post_ids: list[int] = []
    for row in rows:
        if int(row["is_linked"] or 0):
            linked_post_count += 1
        if _keyword_hits(str(row["content"] or ""), keywords):
            post_keyword_match_count += 1
            if len(sample_post_ids) < 3:
                sample_post_ids.append(int(row["id"]))

    return {
        "post_keyword_match_count": post_keyword_match_count,
        "linked_post_count": linked_post_count,
        "sample_post_ids": sample_post_ids,
    }


def _diagnose_topic_for_project(
    connection: sqlite3.Connection,
    *,
    topic: dict[str, Any],
    project_id: int,
    keywords: list[str],
    exclude_keywords: list[str],
    week_start_iso: str,
) -> dict[str, Any]:
    label = str(topic.get("label") or "")
    description = str(topic.get("description") or "")
    topic_text = f"{label} {description}"
    topic_id = topic.get("topic_id")
    if topic_id is None:
        topic_id = _topic_id_for_label(connection, label)

    exclude_hits = _keyword_hits(topic_text, exclude_keywords)
    keyword_hits = _keyword_hits(topic_text, keywords)
    post_stats = _post_match_stats(
        connection,
        topic_id=int(topic_id) if topic_id is not None else None,
        project_id=project_id,
        keywords=keywords,
        week_start_iso=week_start_iso,
    )

    status = "dropped"
    reason = "no keyword overlap in digest topic or recent topic posts"
    if exclude_hits:
        reason = f"excluded keyword: {exclude_hits[0]}"
    elif post_stats["linked_post_count"] > 0:
        status = "linked"
        reason = "already linked through post_project_links"
    elif post_stats["post_keyword_match_count"] > 0:
        status = "candidate_unlinked"
        reason = "recent topic posts match project keywords but no link exists"
    elif keyword_hits:
        status = "candidate_unlinked"
        reason = "digest topic text matches project keywords but no recent linked post exists"

    return {
        "label": label,
        "status": status,
        "reason": reason,
        "topic_keyword_hits": keyword_hits,
        "post_keyword_match_count": post_stats["post_keyword_match_count"],
        "linked_post_count": post_stats["linked_post_count"],
        "sample_post_ids": post_stats["sample_post_ids"],
        "post_count": int(topic.get("post_count") or 0),
    }


def diagnose_project_signal_matching(
    settings: Settings,
    *,
    week_label: str | None = None,
    topic_limit: int = DEFAULT_TOPIC_LIMIT,
) -> dict[str, Any]:
    selected_week = week_label or _current_week_label()
    week_start_iso = _week_start_iso(selected_week)

    with sqlite3.connect(settings.db_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")

        topics = _load_digest_topics(connection, selected_week, topic_limit)
        topic_source = "digest"
        if not topics:
            topics = _load_recent_topics(connection, week_start_iso, topic_limit)
            topic_source = "recent_db"

        project_reports: list[dict[str, Any]] = []
        for project in _load_active_projects(connection):
            config = _find_project_config(str(project["name"] or ""), str(project["github_repo"] or ""))
            keywords = _project_keywords(project, config)
            exclude_keywords = _project_exclude_keywords(config)
            linked_count_row = connection.execute(
                """
                SELECT COUNT(*) AS linked_count
                FROM post_project_links
                WHERE project_id = ?
                """,
                (project["id"],),
            ).fetchone()
            linked_signal_count = int(linked_count_row["linked_count"] or 0) if linked_count_row else 0
            if not keywords:
                project_reports.append(
                    {
                        "project_id": int(project["id"]),
                        "project_name": str(project["name"] or ""),
                        "github_repo": str(project["github_repo"] or ""),
                        "keywords": [],
                        "linked_signal_count": linked_signal_count,
                        "topics": [
                            {
                                "label": str(topic.get("label") or ""),
                                "status": "dropped",
                                "reason": "project has no keywords",
                                "topic_keyword_hits": [],
                                "post_keyword_match_count": 0,
                                "linked_post_count": 0,
                                "sample_post_ids": [],
                                "post_count": int(topic.get("post_count") or 0),
                            }
                            for topic in topics
                        ],
                    }
                )
                continue

            topic_reports = [
                _diagnose_topic_for_project(
                    connection,
                    topic=topic,
                    project_id=int(project["id"]),
                    keywords=keywords,
                    exclude_keywords=exclude_keywords,
                    week_start_iso=week_start_iso,
                )
                for topic in topics
            ]
            project_reports.append(
                {
                    "project_id": int(project["id"]),
                    "project_name": str(project["name"] or ""),
                    "github_repo": str(project["github_repo"] or ""),
                    "keywords": keywords,
                    "linked_signal_count": linked_signal_count,
                    "topics": topic_reports,
                }
            )

    report = {
        "week_label": selected_week,
        "week_start_iso": week_start_iso,
        "topic_source": topic_source,
        "topic_count": len(topics),
        "projects": project_reports,
    }
    LOGGER.info(
        "Project signal diagnostics complete week=%s topic_source=%s projects=%d topics=%d",
        selected_week,
        topic_source,
        len(project_reports),
        len(topics),
    )
    return report


def format_project_signal_diagnostics(report: dict[str, Any]) -> str:
    lines = [
        f"Project signal diagnostics — {report.get('week_label')}",
        f"topic_source={report.get('topic_source')} topics={report.get('topic_count')}",
    ]
    for project in report.get("projects") or []:
        topics = project.get("topics") or []
        linked = sum(1 for topic in topics if topic.get("status") == "linked")
        candidates = sum(1 for topic in topics if topic.get("status") == "candidate_unlinked")
        dropped = sum(1 for topic in topics if topic.get("status") == "dropped")
        keyword_preview = ", ".join((project.get("keywords") or [])[:8]) or "none"
        lines.append("")
        lines.append(
            f"{project.get('project_name')} | linked_signals={project.get('linked_signal_count', 0)} "
            f"| linked_topics={linked} candidate_topics={candidates} dropped_topics={dropped}"
        )
        lines.append(f"  keywords: {keyword_preview}")
        for topic in topics:
            hits = ", ".join(topic.get("topic_keyword_hits") or [])
            sample_ids = ", ".join(str(post_id) for post_id in topic.get("sample_post_ids") or [])
            detail_parts = [
                f"status={topic.get('status')}",
                f"reason={topic.get('reason')}",
            ]
            if hits:
                detail_parts.append(f"hits={hits}")
            if topic.get("post_keyword_match_count"):
                detail_parts.append(f"post_matches={topic.get('post_keyword_match_count')}")
            if sample_ids:
                detail_parts.append(f"sample_posts={sample_ids}")
            lines.append(f"  - {topic.get('label')}: " + "; ".join(detail_parts))
    return "\n".join(lines).rstrip() + "\n"
