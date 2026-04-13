import json
import logging
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import yaml


LOGGER = logging.getLogger(__name__)
PROJECTS_YAML_PATH = Path(__file__).resolve().parents[1] / "config" / "projects.yaml"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _current_week_label() -> str:
    year, week, _ = datetime.now(timezone.utc).isocalendar()
    return f"{year}-W{week:02d}"


def _load_curated_project_configs() -> list[dict]:
    try:
        data = yaml.safe_load(PROJECTS_YAML_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        LOGGER.warning("Failed to load project config from %s", PROJECTS_YAML_PATH, exc_info=True)
        return []
    projects = data.get("projects", [])
    return [project for project in projects if isinstance(project, dict)]


def _find_project_config(project_name: str, github_repo: str) -> dict:
    normalized_name = (project_name or "").strip().lower()
    normalized_repo = (github_repo or "").strip().lower()
    for project in _load_curated_project_configs():
        name = str(project.get("name") or "").strip().lower()
        repo = str(project.get("repo") or "").strip().lower()
        if normalized_name and normalized_name in {name, repo}:
            return project
        if normalized_repo and normalized_repo in {name, repo}:
            return project
    return {}


def _project_aliases(project_name: str, github_repo: str) -> list[str]:
    config = _find_project_config(project_name, github_repo)
    aliases = {
        str(project_name or "").strip(),
        str(github_repo or "").strip(),
        str(config.get("name") or "").strip(),
        str(config.get("repo") or "").strip(),
    }
    return [alias for alias in aliases if alias]


def _feedback_decay_weight(recorded_at: str, half_life_days: float = 45.0) -> float:
    if not recorded_at:
        return 1.0
    try:
        normalized = recorded_at.replace("Z", "+00:00")
        recorded_dt = datetime.fromisoformat(normalized)
    except ValueError:
        return 1.0
    if recorded_dt.tzinfo is None:
        recorded_dt = recorded_dt.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (datetime.now(timezone.utc) - recorded_dt.astimezone(timezone.utc)).total_seconds() / 86400.0)
    return round(0.5 ** (age_days / max(half_life_days, 1.0)), 6)


def refresh_channel_memory(connection: sqlite3.Connection) -> None:
    try:
        rows = connection.execute(
            """
            SELECT
                p.channel_username,
                upt.tag,
                upt.recorded_at
            FROM user_post_tags upt
            INNER JOIN posts p ON p.id = upt.post_id
            ORDER BY p.channel_username ASC
            """
        ).fetchall()
    except sqlite3.Error:
        LOGGER.warning("Failed to refresh channel memory", exc_info=True)
        return
    tag_weights = {
        "strong": 0.28,
        "try_in_project": 0.20,
        "interesting": 0.14,
        "funny": 0.04,
        "read_later": 0.08,
        "low_signal": -0.35,
    }
    stats: dict[str, dict[str, float]] = defaultdict(
        lambda: {
            "positive_tags": 0.0,
            "negative_tags": 0.0,
            "strong_tags": 0.0,
            "try_tags": 0.0,
            "interesting_tags": 0.0,
            "funny_tags": 0.0,
            "low_signal_tags": 0.0,
            "read_later_tags": 0.0,
            "weighted_total": 0.0,
            "feedback_weight": 0.0,
        }
    )
    for row in rows:
        channel = str(row["channel_username"] or "")
        tag = str(row["tag"] or "")
        if not channel or not tag:
            continue
        decay = _feedback_decay_weight(str(row["recorded_at"] or ""))
        item = stats[channel]
        item["weighted_total"] += tag_weights.get(tag, 0.0) * decay
        item["feedback_weight"] += decay
        if tag in {"strong", "try_in_project", "interesting"}:
            item["positive_tags"] += decay
        if tag == "low_signal":
            item["negative_tags"] += decay
        if tag == "strong":
            item["strong_tags"] += decay
        elif tag == "try_in_project":
            item["try_tags"] += decay
        elif tag == "interesting":
            item["interesting_tags"] += decay
        elif tag == "funny":
            item["funny_tags"] += decay
        elif tag == "low_signal":
            item["low_signal_tags"] += decay
        elif tag == "read_later":
            item["read_later_tags"] += decay
    now = _utc_now_iso()
    connection.execute("BEGIN")
    for channel_username, row in stats.items():
        strong_tags = int(round(row["strong_tags"]))
        try_tags = int(round(row["try_tags"]))
        interesting_tags = int(round(row["interesting_tags"]))
        funny_tags = int(round(row["funny_tags"]))
        low_signal_tags = int(round(row["low_signal_tags"]))
        read_later_tags = int(round(row["read_later_tags"]))
        positive_tags = int(round(row["positive_tags"]))
        negative_tags = int(round(row["negative_tags"]))
        feedback_weight = float(row["feedback_weight"] or 0.0)
        average = float(row["weighted_total"] or 0.0) / max(feedback_weight, 1e-6)
        confidence = min(1.0, feedback_weight / 4.0)
        channel_score = max(0.0, min(1.0, 0.5 + average * confidence * 1.5))
        summary_parts: list[str] = []
        summary_parts.append(f"channel score {channel_score:.2f}")
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
                channel_score,
                feedback_weight,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                channel_score = excluded.channel_score,
                feedback_weight = excluded.feedback_weight,
                updated_at = excluded.updated_at
            """,
            (
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
                round(channel_score, 4),
                round(feedback_weight, 4),
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
                   interesting_tags, funny_tags, low_signal_tags, read_later_tags,
                   COALESCE(channel_score, 0.5) AS channel_score,
                   COALESCE(feedback_weight, 0.0) AS feedback_weight,
                   updated_at
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
            "channel_score": float(row["channel_score"] or 0.5),
            "feedback_weight": float(row["feedback_weight"] or 0.0),
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
    aliases = _project_aliases(project_name, github_repo)
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
    recent_signal_rows = connection.execute(
        """
        SELECT po.posted_at, po.channel_username, po.content
        FROM post_project_links ppl
        INNER JOIN posts po ON po.id = ppl.post_id
        WHERE ppl.project_id = ?
        ORDER BY po.posted_at DESC, po.id DESC
        LIMIT 5
        """,
        (project_id,),
    ).fetchall()
    decision_rows = []
    if aliases:
        placeholders = ",".join("?" for _ in aliases)
        decision_rows = connection.execute(
            f"""
            SELECT project_name, status, COALESCE(reason, '') AS reason, recorded_at
            FROM decision_journal
            WHERE project_name IN ({placeholders})
            ORDER BY recorded_at DESC, id DESC
            LIMIT 8
            """,
            aliases,
        ).fetchall()
    recent_signal_summaries = [
        f"{str(row['posted_at'] or '')[:10]} {str(row['channel_username'] or '')}: {' '.join((row['content'] or '').split())[:140]}"
        for row in recent_signal_rows
    ]
    decision_summaries = [
        f"{str(row['recorded_at'] or '')[:10]} {str(row['status'] or '')}: {str(row['reason'] or '')[:140]}"
        for row in decision_rows
    ]
    acted_on_count = sum(1 for row in decision_rows if str(row["status"] or "") == "acted_on")
    deferred_count = sum(1 for row in decision_rows if str(row["status"] or "") == "deferred")
    rejected_count = sum(1 for row in decision_rows if str(row["status"] or "") == "rejected")
    last_decision_at = str(decision_rows[0]["recorded_at"] or "") if decision_rows else ""
    summary = (
        f"{project_name}: {description.strip()} "
        f"Focus: {focus.strip() or 'not specified'}. "
        f"Keywords: {', '.join(keywords) if keywords else 'none'}. "
        f"Linked Telegram signals: {linked_count}. "
        f"Recent decisions: acted_on={acted_on_count}, deferred={deferred_count}, rejected={rejected_count}."
    ).strip()
    open_question_parts: list[str] = []
    if not keywords:
        open_question_parts.append("Keywords are missing or weak; project matching may be too shallow.")
    elif linked_count == 0:
        open_question_parts.append("No linked Telegram signals yet; project relevance likely needs stronger context.")
    if not recent_changes and not decision_rows:
        open_question_parts.append("No recent commits or project-scoped decisions recorded; project context may be stale.")
    elif decision_rows and acted_on_count == 0 and deferred_count > 0:
        open_question_parts.append("Ideas are being deferred but not implemented; clarify current execution horizon.")
    open_questions = " ".join(open_question_parts)
    context_json = json.dumps(
        {
            "description": description,
            "focus": focus,
            "keywords": keywords,
            "github_repo": github_repo,
            "project_aliases": aliases,
            "last_commit_at": last_commit_at,
            "last_linked_post": last_linked_post,
            "recent_changes": recent_changes,
            "linked_telegram_signals": linked_count,
            "recent_linked_signals": recent_signal_summaries,
            "recent_decisions": decision_summaries,
            "decision_counts": {
                "acted_on": acted_on_count,
                "deferred": deferred_count,
                "rejected": rejected_count,
            },
            "last_decision_at": last_decision_at,
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
    connection.execute(
        """
        UPDATE project_context_snapshots
        SET linked_signal_count = ?,
            snapshot_week_label = ?
        WHERE project_id = ?
        """,
        (linked_count, _current_week_label(), project_id),
    )


def refresh_all_project_context_snapshots(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        """
        SELECT id, name, description, keywords, github_repo, last_commit_at
        FROM projects
        WHERE active = 1
        ORDER BY id ASC
        """
    ).fetchall()
    if not rows:
        return
    for row in rows:
        config = _find_project_config(str(row["name"] or ""), str(row["github_repo"] or ""))
        raw_keywords = row["keywords"]
        keywords: list[str] = []
        if raw_keywords:
            try:
                parsed = json.loads(raw_keywords)
            except (TypeError, ValueError):
                parsed = raw_keywords
            if isinstance(parsed, list):
                keywords = [str(item).strip() for item in parsed if str(item).strip()]
            elif isinstance(parsed, str):
                keywords = [part.strip() for part in parsed.split(",") if part.strip()]
        if not keywords:
            keywords = [str(item).strip() for item in config.get("keywords", []) if str(item).strip()]
        refresh_project_context_snapshot(
            connection=connection,
            project_id=int(row["id"]),
            project_name=str(row["name"] or ""),
            description=str(config.get("description") or row["description"] or ""),
            focus=str(config.get("focus") or ""),
            keywords=keywords,
            github_repo=str(row["github_repo"] or config.get("repo") or ""),
            last_commit_at=str(row["last_commit_at"] or ""),
            recent_changes=[],
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
