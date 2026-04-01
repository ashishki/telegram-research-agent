"""
score_posts.py — Phase 1 scoring engine.

Assigns signal_score and bucket to each post in the last N days based on 5 dimensions:
  personal_interest, source_quality, technical_depth, novelty, actionability.

All weights and thresholds are read from src/config/scoring.yaml.
Personal taste (boost/downrank lists) is read from src/config/profile.yaml.

Called before digest synthesis so the LLM receives only strong/watch-bucket posts.
"""

import logging
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import yaml

from config.settings import PROJECT_ROOT, Settings
from llm.router import route
from output.project_relevance import score_project_relevance


LOGGER = logging.getLogger(__name__)
CONFIG_DIR = PROJECT_ROOT / "src" / "config"
SCORING_PATH = CONFIG_DIR / "scoring.yaml"
PROFILE_PATH = CONFIG_DIR / "profile.yaml"
PROJECTS_PATH = CONFIG_DIR / "projects.yaml"
TAG_WEIGHTS = {
    "strong": 0.28,
    "try_in_project": 0.20,
    "interesting": 0.14,
    "funny": 0.04,
    "read_later": 0.08,
    "low_signal": -0.35,
}
TAG_PRIORITY = {
    "strong": 0,
    "try_in_project": 1,
    "interesting": 2,
    "funny": 3,
    "read_later": 4,
    "low_signal": 9,
}


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def _load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _load_config() -> tuple[dict, dict]:
    scoring = _load_yaml(SCORING_PATH)
    profile = _load_yaml(PROFILE_PATH)
    return scoring, profile


def _load_projects() -> list[dict]:
    data = _load_yaml(PROJECTS_PATH)
    projects = data.get("projects", [])
    return [project for project in projects if isinstance(project, dict)]


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def _fetch_posts_window(conn: sqlite3.Connection, since_days: int) -> list[sqlite3.Row]:
    cutoff = (datetime.utcnow() - timedelta(days=since_days)).isoformat() + "Z"
    cursor = conn.execute(
        """
        SELECT
            p.id,
            p.channel_username,
            p.posted_at,
            p.content,
            p.url_count,
            p.has_code,
            p.word_count,
            r.view_count
        FROM posts p
        LEFT JOIN raw_posts r ON r.id = p.raw_post_id
        WHERE p.posted_at >= ?
        ORDER BY p.posted_at ASC
        """,
        (cutoff,),
    )
    return cursor.fetchall()


def _fetch_post_topics(conn: sqlite3.Connection, post_ids: list[int]) -> dict[int, list[str]]:
    """Return {post_id: [topic_label, ...]} for the given post IDs."""
    if not post_ids:
        return {}
    placeholders = ",".join(["?"] * len(post_ids))
    sql = (
        "SELECT pt.post_id, t.label"
        " FROM post_topics pt"
        " JOIN topics t ON t.id = pt.topic_id"
        " WHERE pt.post_id IN (" + placeholders + ")"
        " ORDER BY pt.confidence DESC"
    )
    cursor = conn.execute(sql, post_ids)
    result: dict[int, list[str]] = {}
    for row in cursor.fetchall():
        result.setdefault(row["post_id"], []).append(row["label"])
    return result


def _fetch_topic_history(conn: sqlite3.Connection, lookback_weeks: int) -> dict[str, int]:
    """
    Return {topic_label: weeks_seen} for the last lookback_weeks weeks
    (excluding the current week).
    """
    cutoff = (datetime.utcnow() - timedelta(weeks=lookback_weeks)).isoformat() + "Z"
    current_week_start = (datetime.utcnow() - timedelta(days=datetime.utcnow().weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).isoformat() + "Z"
    cursor = conn.execute(
        """
        SELECT t.label, COUNT(DISTINCT strftime('%Y-%W', p.posted_at)) AS weeks_seen
        FROM post_topics pt
        JOIN topics t ON t.id = pt.topic_id
        JOIN posts p ON p.id = pt.post_id
        WHERE p.posted_at >= ? AND p.posted_at < ?
        GROUP BY t.label
        """,
        (cutoff, current_week_start),
    )
    return {row["label"]: row["weeks_seen"] for row in cursor.fetchall()}


def _fetch_channel_max_views(conn: sqlite3.Connection, since_days: int) -> dict[str, int]:
    """Return {channel_username: max_view_count} for normalizing within-channel view counts."""
    cutoff = (datetime.utcnow() - timedelta(days=since_days)).isoformat() + "Z"
    cursor = conn.execute(
        """
        SELECT p.channel_username, MAX(r.view_count) AS max_views
        FROM posts p
        LEFT JOIN raw_posts r ON r.id = p.raw_post_id
        WHERE p.posted_at >= ?
        GROUP BY p.channel_username
        """,
        (cutoff,),
    )
    return {row["channel_username"]: row["max_views"] or 1 for row in cursor.fetchall()}


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _fetch_user_preference_signals(
    conn: sqlite3.Connection,
    lookback_days: int = 120,
) -> tuple[dict[int, str], dict[str, float]]:
    cutoff = (datetime.utcnow() - timedelta(days=lookback_days)).isoformat() + "Z"
    rows = conn.execute(
        """
        SELECT
            upt.post_id,
            upt.tag,
            p.channel_username,
            upt.recorded_at
        FROM user_post_tags upt
        INNER JOIN posts p ON p.id = upt.post_id
        WHERE upt.recorded_at >= ?
        ORDER BY upt.recorded_at DESC, upt.id DESC
        """,
        (cutoff,),
    ).fetchall()

    post_tags: dict[int, list[str]] = defaultdict(list)
    channel_totals: dict[str, float] = defaultdict(float)
    channel_counts: dict[str, int] = defaultdict(int)
    for row in rows:
        post_id = int(row["post_id"])
        tag = str(row["tag"] or "")
        channel = str(row["channel_username"] or "")
        if not tag:
            continue
        post_tags[post_id].append(tag)
        if channel:
            channel_totals[channel] += TAG_WEIGHTS.get(tag, 0.0)
            channel_counts[channel] += 1

    primary_tags = {
        post_id: sorted(tags, key=lambda item: TAG_PRIORITY.get(item, 99))[0]
        for post_id, tags in post_tags.items()
        if tags
    }
    channel_biases: dict[str, float] = {}
    for channel, total in channel_totals.items():
        count = channel_counts[channel]
        average = total / max(count, 1)
        confidence = min(1.0, count / 4.0)
        channel_biases[channel] = round(_clamp(average * confidence, -0.22, 0.22), 4)
    return primary_tags, channel_biases


# ---------------------------------------------------------------------------
# Scoring dimensions
# ---------------------------------------------------------------------------

def _score_personal_interest(
    topic_labels: list[str],
    boost_topics: list[str],
    downrank_topics: list[str],
) -> float:
    """
    Returns a score in [0, 1] based on how well the post's topics match
    the user's interest profile.

    Strategy:
    - Any boost match → high score (0.85 base + bonus per additional match)
    - Any downrank match → low score (0.10 base)
    - No match → neutral (0.45)
    - Boost takes precedence over downrank.
    """
    if not topic_labels:
        return 0.40  # unclassified posts get slightly below neutral

    content_lower = " ".join(topic_labels).lower()

    boost_hits = sum(
        1 for term in boost_topics if term.lower() in content_lower
    )
    downrank_hits = sum(
        1 for term in downrank_topics if term.lower() in content_lower
    )

    if boost_hits > 0:
        # Each additional boost match adds a small bonus (capped at 1.0)
        return min(1.0, 0.75 + boost_hits * 0.05)
    if downrank_hits > 0:
        return 0.10
    return 0.45


def _score_source_quality(
    channel_username: str,
    view_count: int | None,
    channel_max_views: dict[str, int],
    channel_priority_weights: dict[str, float],
    downrank_sources: list[str],
    channels_config: dict,
) -> float:
    """
    Returns a score in [0, 1].
    channel_priority_weight × (view_count / channel_max_views).
    Downrank sources are hard-penalized regardless of view count.
    """
    if channel_username in downrank_sources:
        return 0.05

    # Look up priority from channels config
    priority = "medium"
    for ch in channels_config.get("channels", []):
        if ch.get("username", "").lstrip("@") == channel_username.lstrip("@"):
            priority = ch.get("priority", "medium")
            break

    base_weight = channel_priority_weights.get(priority, 0.6)
    max_views = channel_max_views.get(channel_username, 1)
    view_ratio = min(1.0, (view_count or 0) / max_views)
    return round(base_weight * view_ratio, 4)


def _fetch_latest_silhouette_score(conn: sqlite3.Connection) -> float:
    """Return the silhouette_score from the most recent cluster run, or 0.5 as default."""
    try:
        row = conn.execute(
            "SELECT silhouette_score FROM cluster_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row and row[0] is not None:
            score = float(row[0])
            return max(0.0, min(1.0, score))
    except sqlite3.Error:
        pass
    return 0.5


def _score_technical_depth(
    has_code: int,
    url_count: int,
    word_count: int,
    depth_weights: dict[str, float],
    coherence_score: float = 0.5,
) -> float:
    """
    Returns a score in [0, 1] based on structural proxies for depth.
    """
    # has_code: binary → 0 or 1
    code_score = float(has_code)

    # url_count: 0 = 0, 1 = 0.5, ≥2 = 1.0
    url_score = min(1.0, url_count / 2.0)

    # word_count: 0 at 0 words, 1.0 at ≥80 words
    word_score = min(1.0, word_count / 80.0)

    return round(
        code_score * depth_weights.get("has_code", 0.35)
        + url_score * depth_weights.get("url_count", 0.25)
        + word_score * depth_weights.get("word_count", 0.25)
        + coherence_score * depth_weights.get("cluster_coherence", 0.15),
        4,
    )


def _score_novelty(
    topic_labels: list[str],
    topic_history: dict[str, int],
    lookback_weeks: int,
    new_cluster_score: float,
    recurring_penalty: float,
) -> float:
    """
    Returns a score based on how new/recurring the topic is.
    - All topics new (0 prior weeks): new_cluster_score
    - Any topic appearing all lookback_weeks: recurring_penalty
    - Otherwise: linearly interpolated
    """
    if not topic_labels:
        return 0.5  # unknown novelty

    max_weeks_seen = max(topic_history.get(label, 0) for label in topic_labels)

    if max_weeks_seen == 0:
        return new_cluster_score
    if max_weeks_seen >= lookback_weeks:
        return recurring_penalty
    # Linear interpolation between new and recurring
    ratio = max_weeks_seen / lookback_weeks
    return round(new_cluster_score - ratio * (new_cluster_score - recurring_penalty), 4)


def _score_actionability(
    has_code: int,
    url_count: int,
    word_count: int,
    actionability_scores: dict[str, float],
) -> float:
    """
    Phase 1 heuristic actionability (Haiku classification added in Phase 2).
    Infers one of: implement, pattern, awareness, noise.
    """
    if has_code:
        return actionability_scores.get("implement", 1.0)
    if url_count >= 2:
        return actionability_scores.get("pattern", 0.7)
    if word_count >= 80:
        return actionability_scores.get("awareness", 0.3)
    return actionability_scores.get("noise", 0.0)


def _score_recency(posted_at: str, since_days: int) -> float:
    """Return a 0-1 score where newer posts within the scoring window rank higher."""
    if not posted_at:
        return 0.0

    try:
        normalized = posted_at.replace("Z", "+00:00")
        posted_dt = datetime.fromisoformat(normalized)
    except ValueError:
        return 0.0

    if posted_dt.tzinfo is None:
        posted_dt = posted_dt.replace(tzinfo=timezone.utc)

    age_seconds = max(0.0, (datetime.now(timezone.utc) - posted_dt).total_seconds())
    window_seconds = max(float(since_days), 1.0) * 86400.0
    return round(max(0.0, 1.0 - min(age_seconds / window_seconds, 1.0)), 4)


def _score_engagement(
    channel_username: str,
    view_count: int | None,
    channel_max_views: dict[str, int],
) -> float:
    max_views = channel_max_views.get(channel_username, 1)
    if max_views <= 0:
        return 0.0
    return round(min(1.0, (view_count or 0) / max_views), 4)


# ---------------------------------------------------------------------------
# Cultural bucket detection
# ---------------------------------------------------------------------------

def _is_cultural(content: str, cultural_keywords: list[str]) -> bool:
    content_lower = content.lower()
    return any(kw.lower() in content_lower for kw in cultural_keywords)


# ---------------------------------------------------------------------------
# Main scoring function
# ---------------------------------------------------------------------------

def score_posts(
    settings: Settings,
    since_days: int = 7,
) -> dict:
    """
    Score all posts in the last `since_days` days.
    Writes signal_score and bucket to the posts table.
    Returns a summary dict with bucket counts and avg score.
    """
    scoring_cfg, profile_cfg = _load_config()
    try:
        projects = _load_projects()
    except Exception:
        LOGGER.warning("Failed to load projects config from %s", PROJECTS_PATH, exc_info=True)
        projects = []

    weights = scoring_cfg.get("weights", {})
    channel_priority_weights = scoring_cfg.get("channel_priority_weights", {"high": 1.0, "medium": 0.6, "low": 0.2})
    depth_weights = scoring_cfg.get("technical_depth_weights", {})
    novelty_cfg = scoring_cfg.get("novelty", {})
    actionability_scores = scoring_cfg.get("actionability_scores", {})
    bucket_cfg = scoring_cfg.get("buckets", {})

    strong_threshold = bucket_cfg.get("strong", {}).get("min_score", 0.75)
    watch_threshold = bucket_cfg.get("watch", {}).get("min_score", 0.45)
    strong_max = bucket_cfg.get("strong", {}).get("max_items", 3)
    watch_max = bucket_cfg.get("watch", {}).get("max_items", 3)
    cultural_max = bucket_cfg.get("cultural", {}).get("max_items", 1)

    boost_topics = profile_cfg.get("boost_topics", [])
    downrank_topics = profile_cfg.get("downrank_topics", [])
    downrank_sources = profile_cfg.get("downrank_sources", [])
    cultural_keywords = profile_cfg.get("cultural_keywords", [])

    # Load channels config for priority lookup
    channels_config_path = CONFIG_DIR / "channels.yaml"
    channels_config = _load_yaml(channels_config_path)

    lookback_weeks = novelty_cfg.get("lookback_weeks", 4)
    new_cluster_score = novelty_cfg.get("new_cluster_min_score", 0.80)
    recurring_penalty = novelty_cfg.get("recurring_cluster_penalty", 0.30)

    w_interest = weights.get("personal_interest", 0.30)
    w_source = weights.get("source_quality", 0.20)
    w_depth = weights.get("technical_depth", 0.20)
    w_novelty = weights.get("novelty", 0.15)
    w_action = weights.get("actionability", 0.15)

    summary = {"scored": 0, "strong": 0, "watch": 0, "cultural": 0, "noise": 0, "errors": 0}
    score_run_id = str(uuid4())
    scored_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    with sqlite3.connect(settings.db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")

        posts = _fetch_posts_window(conn, since_days)
        if not posts:
            LOGGER.info("score_posts: no posts found in last %d days", since_days)
            return summary

        post_ids = [p["id"] for p in posts]
        post_topics_map = _fetch_post_topics(conn, post_ids)
        topic_history = _fetch_topic_history(conn, lookback_weeks)
        channel_max_views = _fetch_channel_max_views(conn, since_days)
        coherence_score = _fetch_latest_silhouette_score(conn)

        explicit_tags_by_post, channel_biases = _fetch_user_preference_signals(conn)
        scored_rows: list[tuple[float, str, float, str, str, str, float, float, str | None, str, int]] = []

        for post in posts:
            try:
                post_id = post["id"]
                topic_labels = post_topics_map.get(post_id, [])

                d_interest = _score_personal_interest(topic_labels, boost_topics, downrank_topics)
                d_source = _score_source_quality(
                    post["channel_username"],
                    post["view_count"],
                    channel_max_views,
                    channel_priority_weights,
                    downrank_sources,
                    channels_config,
                )
                d_depth = _score_technical_depth(
                    post["has_code"],
                    post["url_count"],
                    post["word_count"],
                    depth_weights,
                    coherence_score=coherence_score,
                )
                d_novelty = _score_novelty(
                    topic_labels,
                    topic_history,
                    lookback_weeks,
                    new_cluster_score,
                    recurring_penalty,
                )
                d_action = _score_actionability(
                    post["has_code"],
                    post["url_count"],
                    post["word_count"],
                    actionability_scores,
                )
                d_recency = _score_recency(post["posted_at"], since_days)
                d_engagement = _score_engagement(
                    post["channel_username"],
                    post["view_count"],
                    channel_max_views,
                )

                signal_score = round(
                    d_interest * w_interest
                    + d_source * w_source
                    + d_depth * w_depth
                    + d_novelty * w_novelty
                    + d_action * w_action,
                    4,
                )
                explicit_tag = explicit_tags_by_post.get(post_id)
                channel_bias = channel_biases.get(post["channel_username"], 0.0)
                explicit_bias = TAG_WEIGHTS.get(explicit_tag or "", 0.0)
                user_preference_score = round(channel_bias + explicit_bias, 4)
                adjusted_score = round(_clamp(signal_score + user_preference_score), 4)

                # Bucket assignment (scores first; cultural override applied after)
                content = post["content"] or ""
                if adjusted_score >= strong_threshold:
                    bucket = "strong"
                elif adjusted_score >= watch_threshold:
                    bucket = "watch"
                elif _is_cultural(content, cultural_keywords):
                    bucket = "cultural"
                else:
                    bucket = "noise"

                if explicit_tag == "low_signal":
                    adjusted_score = min(adjusted_score, 0.15)
                    bucket = "noise"
                elif explicit_tag == "strong":
                    adjusted_score = max(adjusted_score, strong_threshold + 0.10)
                    bucket = "strong"
                elif explicit_tag == "try_in_project":
                    adjusted_score = max(adjusted_score, watch_threshold + 0.12)
                    bucket = "watch" if adjusted_score < strong_threshold else "strong"
                elif explicit_tag == "interesting":
                    adjusted_score = max(adjusted_score, watch_threshold + 0.04)
                    bucket = "watch" if adjusted_score < strong_threshold else "strong"
                elif explicit_tag == "read_later" and bucket == "noise":
                    adjusted_score = max(adjusted_score, watch_threshold)
                    bucket = "watch"
                elif explicit_tag == "funny":
                    bucket = "cultural"

                routed_model = route("per_post", signal_score=adjusted_score)
                project_matches = score_project_relevance(content, projects)
                project_relevance_score = max(
                    (float(match.get("score") or 0.0) for match in project_matches),
                    default=0.0,
                )
                score_breakdown = json.dumps(
                    {
                        "recency": d_recency,
                        "engagement": d_engagement,
                        "topic_relevance": d_interest,
                        "source_quality": d_source,
                        "novelty": d_novelty,
                    }
                )
                scored_rows.append(
                    (
                        signal_score,
                        bucket,
                        project_relevance_score,
                        routed_model,
                        score_run_id,
                        scored_at,
                        user_preference_score,
                        adjusted_score,
                        explicit_tag,
                        score_breakdown,
                        post_id,
                    )
                )
                summary["scored"] += 1

            except Exception:
                LOGGER.warning("Scoring failed for post_id=%s", post.get("id"), exc_info=True)
                summary["errors"] += 1
                continue

        # Write scores to DB
        conn.execute("BEGIN")
        conn.executemany(
            (
                "UPDATE posts SET signal_score = ?, bucket = ?, project_relevance_score = ?, "
                "routed_model = ?, score_run_id = ?, scored_at = ?, user_preference_score = ?, "
                "user_adjusted_score = ?, user_override_tag = ?, score_breakdown = ? WHERE id = ?"
            ),
            scored_rows,
        )
        conn.commit()

    # Apply per-bucket caps: re-cap at max items by downgrading extras to noise
    # (cap enforcement is done at digest-generation time, not here — we store raw scores)
    # Count buckets for summary
    for row in scored_rows:
        bucket = row[1]
        summary[bucket] = summary.get(bucket, 0) + 1

    avg_score = (
        round(sum(row[0] for row in scored_rows) / len(scored_rows), 4)
        if scored_rows else 0.0
    )
    summary["avg_signal_score"] = avg_score

    LOGGER.info(
        "score_posts complete scored=%d strong=%d watch=%d cultural=%d noise=%d avg=%.4f errors=%d",
        summary["scored"],
        summary.get("strong", 0),
        summary.get("watch", 0),
        summary.get("cultural", 0),
        summary.get("noise", 0),
        avg_score,
        summary["errors"],
    )
    return summary
