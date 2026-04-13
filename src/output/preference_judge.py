import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone

from db.retrieval import fetch_evidence_items
from llm.client import LLMClient
from output.context_memory import (
    load_channel_memory,
    load_project_context,
    refresh_all_project_context_snapshots,
    refresh_channel_memory,
)


LOGGER = logging.getLogger(__name__)
ACTIVE_PROJECTS = {
    "ai-workflow-playbook",
    "telegram-research-agent",
    "film-school-assistant",
    "gdev-agent",
}
VISIBLE_TAGS = {"strong", "interesting", "try_in_project", "funny"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _truncate(text: str | None, limit: int = 900) -> str:
    compact = " ".join((text or "").split())
    return compact[:limit]


def _fetch_tagged_examples(connection: sqlite3.Connection, limit_per_tag: int = 3) -> list[dict]:
    rows = connection.execute(
        """
        SELECT
            upt.tag,
            COALESCE(upt.note, '') AS note,
            p.id,
            p.channel_username,
            p.content,
            p.signal_score,
            r.message_url
        FROM user_post_tags upt
        INNER JOIN posts p ON p.id = upt.post_id
        INNER JOIN raw_posts r ON r.id = p.raw_post_id
        WHERE upt.tag IN ('strong', 'interesting', 'try_in_project', 'funny', 'low_signal')
        ORDER BY upt.recorded_at DESC, upt.id DESC
        """
    ).fetchall()

    counts: dict[str, int] = {}
    examples: list[dict] = []
    for row in rows:
        tag = str(row["tag"])
        counts.setdefault(tag, 0)
        if counts[tag] >= limit_per_tag:
            continue
        counts[tag] += 1
        examples.append(
            {
                "tag": tag,
                "note": str(row["note"] or ""),
                "channel": str(row["channel_username"] or ""),
                "signal_score": float(row["signal_score"] or 0.0),
                "content": _truncate(row["content"], 360),
                "url": str(row["message_url"] or ""),
            }
        )
    return examples


def _fetch_candidates(connection: sqlite3.Connection, lookback_days: int = 21, limit: int = 24) -> list[dict]:
    cutoff = (_utc_now() - timedelta(days=lookback_days)).isoformat().replace("+00:00", "Z")
    rows = connection.execute(
        """
        SELECT
            p.id,
            p.channel_username,
            p.content,
            p.signal_score,
            COALESCE(p.user_adjusted_score, p.signal_score, 0) AS ranking_score,
            p.bucket,
            p.project_relevance_score,
            COALESCE(upt.tag, '') AS user_tag,
            COALESCE(upt.note, '') AS user_note,
            r.message_url
        FROM posts p
        INNER JOIN raw_posts r ON r.id = p.raw_post_id
        LEFT JOIN user_post_tags upt ON upt.post_id = p.id
        WHERE p.posted_at >= ? AND p.scored_at IS NOT NULL
        ORDER BY
            CASE WHEN upt.tag IN ('strong', 'interesting', 'try_in_project', 'funny') THEN 0 ELSE 1 END,
            CASE WHEN upt.tag = 'low_signal' THEN 1 ELSE 0 END,
            COALESCE(p.user_adjusted_score, p.signal_score, 0) DESC,
            COALESCE(p.project_relevance_score, 0) DESC,
            p.posted_at DESC
        LIMIT ?
        """,
        (cutoff, limit),
    ).fetchall()
    candidates: list[dict] = []
    seen: set[int] = set()
    for row in rows:
        post_id = int(row["id"])
        if post_id in seen:
            continue
        seen.add(post_id)
        candidates.append(
            {
                "post_id": post_id,
                "channel": str(row["channel_username"] or ""),
                "content": _truncate(row["content"], 420),
                "signal_score": float(row["signal_score"] or 0.0),
                "ranking_score": float(row["ranking_score"] or 0.0),
                "bucket": str(row["bucket"] or ""),
                "project_relevance_score": float(row["project_relevance_score"] or 0.0),
                "user_tag": str(row["user_tag"] or ""),
                "user_note": str(row["user_note"] or ""),
                "url": str(row["message_url"] or ""),
            }
        )
    return candidates


def _active_projects(projects: list[dict] | None) -> list[dict]:
    if not projects:
        return []
    result = []
    for project in projects:
        name = str(project.get("name") or "")
        if name not in ACTIVE_PROJECTS:
            continue
        result.append(
            {
                "name": name,
                "description": str(project.get("description") or ""),
                "focus": str(project.get("focus") or ""),
            }
        )
    return result


def _project_names(projects: list[dict]) -> list[str]:
    return [str(project.get("name") or "").strip() for project in projects if str(project.get("name") or "").strip()]


def _last_n_week_labels(n: int = 3) -> tuple[str, str]:
    """Return (start_week, end_week) for the last n ISO weeks including current."""
    now = _utc_now()
    end_dt = now
    start_dt = now - timedelta(weeks=n - 1)
    year_end, week_end, _ = end_dt.isocalendar()
    year_start, week_start, _ = start_dt.isocalendar()
    return f"{year_start}-W{week_start:02d}", f"{year_end}-W{week_end:02d}"


def _fetch_project_evidence(
    connection: sqlite3.Connection,
    project_names: list[str],
    n_weeks: int = 3,
) -> dict[str, list[dict]]:
    """Return recent scoped evidence items keyed by project_name."""
    if not project_names:
        return {}
    week_range = _last_n_week_labels(n_weeks)
    result: dict[str, list[dict]] = {}
    for name in project_names:
        try:
            items = fetch_evidence_items(
                connection,
                project_name=name,
                week_range=list(week_range),
                limit=5,
            )
        except Exception:
            LOGGER.warning("Evidence fetch failed for project=%s", name, exc_info=True)
            items = []
        result[name] = items
    return result


def _compact_project_evidence(evidence_by_project: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """Compact evidence items to a token-safe representation for the prompt."""
    compact: dict[str, list[dict]] = {}
    for project_name, items in evidence_by_project.items():
        compact[project_name] = [
            {
                "week": str(item.get("week_label") or ""),
                "kind": str(item.get("evidence_kind") or ""),
                "channel": str(item.get("source_channel") or ""),
                "excerpt": str(item.get("excerpt_text") or "")[:280],
            }
            for item in items
        ]
    return compact


def _compact_channel_memory(channel_memory: dict[str, dict]) -> dict[str, dict]:
    compact: dict[str, dict] = {}
    for channel, item in channel_memory.items():
        compact[channel] = {
            "summary": str(item.get("summary") or "")[:180],
            "positive_tags": int(item.get("positive_tags") or 0),
            "negative_tags": int(item.get("negative_tags") or 0),
            "strong_tags": int(item.get("strong_tags") or 0),
            "try_tags": int(item.get("try_tags") or 0),
            "interesting_tags": int(item.get("interesting_tags") or 0),
            "low_signal_tags": int(item.get("low_signal_tags") or 0),
            "channel_score": float(item.get("channel_score") or 0.5),
            "feedback_weight": float(item.get("feedback_weight") or 0.0),
        }
    return compact


def _compact_project_context(project_context: list[dict]) -> list[dict]:
    compact: list[dict] = []
    for item in project_context:
        context = item.get("context") if isinstance(item.get("context"), dict) else {}
        compact.append(
            {
                "project_name": str(item.get("project_name") or ""),
                "summary": str(item.get("summary") or "")[:220],
                "recent_changes": str(item.get("recent_changes") or "")[:260],
                "open_questions": str(item.get("open_questions") or "")[:180],
                "focus": str(context.get("focus") or "")[:180],
                "keywords": list(context.get("keywords") or [])[:12],
            }
        )
    return compact


def _judge_batch_once(
    candidates: list[dict],
    examples: list[dict],
    projects: list[dict],
    channel_memory: dict[str, dict],
    project_context: list[dict],
    project_evidence: dict | None = None,
) -> dict[int, dict]:
    if not candidates:
        return {}
    system = (
        "You are a personal research preference judge for one specific user. "
        "Your job is to infer what matters to this user from tagged examples and map candidate posts into "
        "reader-facing categories. Use the user's notes only as training signal, not as report prose. "
        "Return strict JSON."
    )
    _evidence_section = (
        "Recent evidence for projects (last 3 weeks, scoped per project):\n"
        f"{json.dumps(_compact_project_evidence(project_evidence or {}), ensure_ascii=False, indent=2)}\n\n"
    )
    prompt = (
        "Active projects:\n"
        f"{json.dumps(projects, ensure_ascii=False, indent=2)}\n\n"
        "Project context snapshots:\n"
        f"{json.dumps(_compact_project_context(project_context), ensure_ascii=False, indent=2)}\n\n"
        + _evidence_section
        + "Channel memory:\n"
        f"{json.dumps(_compact_channel_memory(channel_memory), ensure_ascii=False, indent=2)}\n\n"
        "Tagged examples showing the user's taste:\n"
        f"{json.dumps(examples, ensure_ascii=False, indent=2)}\n\n"
        "Candidate posts to judge:\n"
        f"{json.dumps(candidates, ensure_ascii=False, indent=2)}\n\n"
        "For each candidate return an object with keys:\n"
        "- post_id: integer\n"
        "- include: boolean\n"
        "- category: one of strong, try_in_project, interesting, funny, ignore\n"
        "- title: short reader-facing title in Russian\n"
        "- key_takeaway: one concise Russian extraction of the most important idea in the post, so the user can avoid opening the source unless needed\n"
        "- why_now: one concise Russian explanation of why this matters now for the user's current work\n"
        "- project_name: one of active project names or empty string\n"
        "- project_application: short Russian explanation of exactly what from the post is useful for the project, and what the next move could be, or empty string\n"
        "- confidence: number 0..1\n"
        "Be selective. Prefer fewer items. Ignore generic hype, broad news and shallow benchmarking unless it clearly fits the user's tagged taste.\n"
        "Do not repeat the user's raw notes. Use them only as training signal.\n"
        "Write for the end reader, not for another model.\n"
        "Return JSON as {\"results\": [...]}."
    )
    response = LLMClient.complete_json(prompt=prompt, system=system, category="preference_judge")
    if not isinstance(response, dict):
        return {}
    raw_results = response.get("results")
    if not isinstance(raw_results, list):
        return {}

    judged: dict[int, dict] = {}
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        try:
            post_id = int(item.get("post_id"))
        except Exception:
            continue
        judged[post_id] = {
            "include": bool(item.get("include", False)),
            "category": str(item.get("category") or "ignore"),
            "title": str(item.get("title") or "").strip(),
            "key_takeaway": str(item.get("key_takeaway") or "").strip(),
            "why_now": str(item.get("why_now") or "").strip(),
            "project_name": str(item.get("project_name") or "").strip(),
            "project_application": str(item.get("project_application") or "").strip(),
            "confidence": float(item.get("confidence") or 0.0),
        }
    return judged


def _judge_batch(
    candidates: list[dict],
    examples: list[dict],
    projects: list[dict],
    channel_memory: dict[str, dict],
    project_context: list[dict],
    batch_size: int = 4,
    project_evidence: dict | None = None,
) -> dict[int, dict]:
    judged: dict[int, dict] = {}
    for start in range(0, len(candidates), batch_size):
        batch = candidates[start : start + batch_size]
        try:
            judged.update(_judge_batch_once(batch, examples, projects, channel_memory, project_context, project_evidence))
        except Exception:
            LOGGER.warning(
                "Preference judge batch failed start=%d size=%d; skipping batch",
                start,
                len(batch),
                exc_info=True,
            )
            break
    return judged


def judge_recent_posts(db_path: str, projects: list[dict] | None, lookback_days: int = 21) -> dict[int, dict]:
    try:
        with sqlite3.connect(db_path) as connection:
            connection.row_factory = sqlite3.Row
            refresh_channel_memory(connection)
            refresh_all_project_context_snapshots(connection)
            examples = _fetch_tagged_examples(connection)
            candidates = _fetch_candidates(connection, lookback_days=lookback_days)
            active_projects = _active_projects(projects)
            channel_memory = load_channel_memory(connection, [str(candidate.get("channel") or "") for candidate in candidates])
            project_context = load_project_context(connection, _project_names(active_projects))
            project_evidence = _fetch_project_evidence(connection, _project_names(active_projects))
    except sqlite3.Error:
        LOGGER.warning("Preference judge skipped because preference tables are unavailable", exc_info=True)
        return {}
    if not examples or not candidates:
        return {}

    judged = _judge_batch(candidates, examples, active_projects, channel_memory, project_context, project_evidence=project_evidence)
    LOGGER.info("Preference judge evaluated candidates=%d judged=%d", len(candidates), len(judged))
    return judged
