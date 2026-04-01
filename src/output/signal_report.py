import json
import logging
import os
import sqlite3
from collections import Counter
from pathlib import Path

import yaml

from output.personalize import apply_personalization
from output.preference_judge import judge_recent_posts
from output.project_relevance import score_project_relevance


LOGGER = logging.getLogger(__name__)
PROJECTS_YAML_PATH = Path(__file__).resolve().parents[1] / "config" / "projects.yaml"
PROFILE_YAML_PATH = Path(__file__).resolve().parents[1] / "config" / "profile.yaml"

TAG_PRIORITY = {
    "strong": 0,
    "try_in_project": 1,
    "interesting": 2,
    "funny": 3,
    "read_later": 4,
    "low_signal": 9,
}
VISIBLE_TAGS = ("strong", "try_in_project", "interesting", "funny", "read_later")
MANUAL_HEADING_BY_TAG = {
    "strong": "What Matters This Week",
    "try_in_project": "Things To Try",
    "interesting": "Keep In View",
    "funny": "Funny / Cultural",
    "read_later": "Read Later",
}


def _load_projects() -> list[dict] | None:
    try:
        data = yaml.safe_load(PROJECTS_YAML_PATH.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        LOGGER.warning("Failed to load projects config from %s", PROJECTS_YAML_PATH, exc_info=True)
        return None
    projects = data.get("projects", [])
    return [project for project in projects if isinstance(project, dict)]


def _load_profile() -> dict | None:
    try:
        data = yaml.safe_load(PROFILE_YAML_PATH.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        LOGGER.warning("Failed to load profile config from %s", PROFILE_YAML_PATH, exc_info=True)
        return None
    return data if isinstance(data, dict) else {}


def _truncate_words(text: str | None, limit: int) -> str:
    words = (text or "").split()
    return " ".join(words[:limit])


def _format_source_suffix(message_url: str | None) -> str:
    url = (message_url or "").strip()
    return f" | Source: {url}" if url else ""


def _load_previous_quality_metrics() -> dict | None:
    db_path = os.environ.get("AGENT_DB_PATH", "").strip()
    if not db_path:
        return None
    try:
        with sqlite3.connect(db_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """
                SELECT strong_count, watch_count, noise_count
                FROM quality_metrics
                ORDER BY computed_at DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
    except sqlite3.Error:
        LOGGER.warning("Failed to load previous quality metrics from %s", db_path, exc_info=True)
        return None
    return dict(row) if row is not None else None


def _build_what_changed_lines(bucket_counts: Counter) -> list[str]:
    previous = _load_previous_quality_metrics()
    if previous is None:
        return ["No comparison baseline available."]

    lines = []
    for bucket_name in ("strong", "watch", "noise"):
        current = int(bucket_counts.get(bucket_name, 0))
        prior = int(previous.get(f"{bucket_name}_count") or 0)
        delta = current - prior
        lines.append(f"- {bucket_name}: {current} (was {prior}, {delta:+d})")
    return lines


def _load_user_tag_details(post_ids: list[int], settings) -> dict[int, list[dict[str, str]]]:
    if not post_ids:
        return {}
    db_path = ""
    if settings is not None:
        db_path = str(getattr(settings, "db_path", "") or "").strip()
    if not db_path:
        db_path = os.environ.get("AGENT_DB_PATH", "").strip()
    if not db_path:
        return {}
    placeholders = ",".join("?" for _ in post_ids)
    try:
        with sqlite3.connect(db_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                f"""
                SELECT post_id, tag, COALESCE(note, '') AS note
                FROM user_post_tags
                WHERE post_id IN ({placeholders})
                ORDER BY recorded_at DESC, id DESC
                """,
                post_ids,
            ).fetchall()
    except sqlite3.Error:
        LOGGER.warning("Failed to load user tags", exc_info=True)
        return {}

    result: dict[int, list[dict[str, str]]] = {}
    for row in rows:
        post_id = int(row["post_id"])
        result.setdefault(post_id, [])
        result[post_id].append({"tag": str(row["tag"]), "note": str(row["note"] or "")})
    return result


def _highest_priority_tag(tag_details: list[dict[str, str]]) -> str | None:
    if not tag_details:
        return None
    ordered = sorted(tag_details, key=lambda item: TAG_PRIORITY.get(item["tag"], 99))
    return ordered[0]["tag"]


def _note_for_tag(tag_details: list[dict[str, str]], tag: str) -> str:
    for item in tag_details:
        if item["tag"] == tag and item["note"].strip():
            return item["note"].strip()
    return ""


def _render_signal(
    post: dict,
    *,
    title: str = "",
    key_takeaway: str = "",
    why_now: str = "",
    project_application: str = "",
) -> str:
    source = (post.get("message_url") or "").strip()
    header = title.strip() or _truncate_words(post.get("content"), 12)
    lines = [f"- **{header}**"]
    if key_takeaway.strip():
        lines.append(f"  Key takeaway: {key_takeaway.strip()}")
    if why_now.strip():
        lines.append(f"  Why now: {why_now.strip()}")
    if project_application.strip():
        lines.append(f"  Project application: {project_application.strip()}")
    if source:
        lines.append(f"  Source: {source}")
    return "\n".join(lines)


def _sort_posts_for_brief(posts: list[dict], tag_details_by_post: dict[int, list[dict[str, str]]]) -> list[dict]:
    def sort_key(post: dict) -> tuple[float, float]:
        post_id = int(post.get("id") or 0)
        primary_tag = _highest_priority_tag(tag_details_by_post.get(post_id, []))
        tag_rank = TAG_PRIORITY.get(primary_tag or "", 5)
        score_rank = -float(post.get("user_adjusted_score") or post.get("signal_score") or 0.0)
        return float(tag_rank), score_rank

    return sorted(posts, key=sort_key)


def _judged(post_id: int, judged_by_post: dict[int, dict]) -> dict:
    return judged_by_post.get(post_id, {})


def _table_exists(db_path: str, table_name: str) -> bool:
    if not db_path:
        return False
    try:
        with sqlite3.connect(db_path) as connection:
            row = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table_name,),
            ).fetchone()
    except sqlite3.Error:
        return False
    return row is not None


def _format_legacy_entry(post: dict) -> str:
    excerpt = _truncate_words(post.get("content"), 24)
    score = float(post.get("signal_score") or 0.0)
    model = str(post.get("routed_model") or "")
    suffix = _format_source_suffix(post.get("message_url"))
    return f"- {excerpt} [score={score:.2f}] [model={model}]{suffix}"


def _build_legacy_project_queue(posts: list[dict], projects: list[dict] | None) -> list[str]:
    if not projects:
        return []
    grouped: dict[str, list[str]] = {}
    for post in posts:
        if str(post.get("bucket") or "") == "noise":
            continue
        matches = score_project_relevance(post.get("content", ""), projects)
        for match in matches:
            score = float(match.get("score") or 0.0)
            if score < 0.30:
                continue
            grouped.setdefault(str(match.get("name") or "unknown"), []).append(
                f"- {_truncate_words(post.get('content'), 18)} [relevance={score:.2f}]"
            )
    if not grouped:
        return []
    lines = ["## Project Action Queue"]
    for project_name in sorted(grouped):
        lines.append(f"**{project_name}**")
        lines.extend(grouped[project_name][:3])
        lines.append("")
    return lines


def _format_legacy_signal_report(posts: list[dict], settings) -> str:
    profile = _load_profile()
    indexed_posts = [{**post, "_original_position": index} for index, post in enumerate(posts)]
    ranked_posts = apply_personalization(indexed_posts, profile) if profile is not None else list(indexed_posts)
    strong_posts = sorted(
        [post for post in ranked_posts if str(post.get("bucket") or "") == "strong"],
        key=lambda post: float(post.get("signal_score") or 0.0),
        reverse=True,
    )
    watch_posts = sorted(
        [post for post in ranked_posts if str(post.get("bucket") or "") == "watch"],
        key=lambda post: float(post.get("signal_score") or 0.0),
        reverse=True,
    )
    cultural_posts = sorted(
        [post for post in ranked_posts if str(post.get("bucket") or "") == "cultural"],
        key=lambda post: float(post.get("signal_score") or 0.0),
        reverse=True,
    )
    noise_posts = [post for post in ranked_posts if str(post.get("bucket") or "") == "noise"]
    bucket_counts = Counter((post.get("bucket") or "noise") for post in ranked_posts)

    decision_lines = ["No decision-grade signals this week."]
    long_strong = next(
        (post for post in strong_posts if int(post.get("word_count") or 0) >= 80),
        strong_posts[0] if strong_posts else None,
    )
    if long_strong is not None:
        decision_lines = [f"- Consider: {_truncate_words(long_strong.get('content'), 20)}"]

    projects = _load_projects()
    project_lines = _build_legacy_project_queue(ranked_posts, projects)
    think_lines = ["No manual preference signals loaded."]
    if settings is not None:
        tag_details = _load_user_tag_details([int(post.get("id") or 0) for post in ranked_posts], settings)
        manual_count = sum(1 for details in tag_details.values() if details)
        think_lines = [f"Manual preference signals loaded for {manual_count} posts."]

    sections: list[str] = [
        "## Strong Signals",
        *( [_format_legacy_entry(post) for post in strong_posts] or ["No strong signals this week."] ),
        "",
        "## Decisions to Consider",
        *decision_lines,
        "",
        "## Watch",
        *( [_format_legacy_entry(post) for post in watch_posts] or ["No watch signals this week."] ),
        "",
        "## Cultural",
        *( [_format_legacy_entry(post) for post in cultural_posts] or ["No cultural signals this week."] ),
        "",
        "## Ignored",
        f"{len(noise_posts)} posts filtered as noise.",
        "",
    ]
    if project_lines:
        sections.extend(project_lines)
    sections.extend(
        [
            "## Think Layer",
            *think_lines,
            "",
            "## Stats",
            f"- strong: {bucket_counts.get('strong', 0)}",
            f"- watch: {bucket_counts.get('watch', 0)}",
            f"- cultural: {bucket_counts.get('cultural', 0)}",
            f"- noise: {bucket_counts.get('noise', 0)}",
            "",
            "## What Changed",
            *_build_what_changed_lines(bucket_counts),
        ]
    )
    return "\n".join(sections).strip() + "\n"


def _build_manual_sections(
    posts: list[dict],
    tag_details_by_post: dict[int, list[dict[str, str]]],
    judged_by_post: dict[int, dict],
) -> list[tuple[str, list[str]]]:
    lines_by_heading: dict[str, list[str]] = {heading: [] for heading in MANUAL_HEADING_BY_TAG.values()}
    for post in posts:
        post_id = int(post.get("id") or 0)
        tag_details = tag_details_by_post.get(post_id, [])
        primary_tag = _highest_priority_tag(tag_details)
        if primary_tag not in VISIBLE_TAGS:
            continue
        heading = MANUAL_HEADING_BY_TAG[primary_tag]
        judged = _judged(post_id, judged_by_post)
        lines_by_heading[heading].append(
            _render_signal(
                post,
                title=str(judged.get("title") or ""),
                key_takeaway=str(judged.get("key_takeaway") or ""),
                why_now=str(judged.get("why_now") or ""),
                project_application=str(judged.get("project_application") or ""),
            )
        )

    order = [
        "What Matters This Week",
        "Things To Try",
        "Keep In View",
        "Funny / Cultural",
        "Read Later",
    ]
    return [(heading, lines_by_heading[heading]) for heading in order if lines_by_heading[heading]]


def _build_project_sections(
    posts: list[dict],
    projects: list[dict] | None,
    tag_details_by_post: dict[int, list[dict[str, str]]],
    judged_by_post: dict[int, dict],
) -> list[str]:
    if not projects:
        return ["No project-specific signals this week."]

    grouped: dict[str, list[str]] = {}
    for post in posts:
        post_id = int(post.get("id") or 0)
        primary_tag = _highest_priority_tag(tag_details_by_post.get(post_id, []))
        if primary_tag == "low_signal":
            continue
        judged = _judged(post_id, judged_by_post)
        judged_project = str(judged.get("project_name") or "").strip()
        if judged_project:
            grouped.setdefault(judged_project, []).append(
                _render_signal(
                    post,
                    title=str(judged.get("title") or ""),
                    key_takeaway=str(judged.get("key_takeaway") or ""),
                    why_now=str(judged.get("why_now") or ""),
                    project_application=str(judged.get("project_application") or ""),
                )
            )
            continue
        matches = score_project_relevance(post.get("content", ""), projects)
        for match in matches:
            score = float(match.get("score") or 0.0)
            if score < 0.30:
                continue
            project_name = str(match.get("name") or "unknown")
            rationale = str(match.get("rationale") or "").strip()
            note = _note_for_tag(tag_details_by_post.get(post_id, []), primary_tag or "")
            detail = rationale or note or "relevant pattern"
            grouped.setdefault(project_name, []).append(
                _render_signal(post, key_takeaway=detail)
            )

    if not grouped:
        return ["No project-specific signals this week."]

    lines: list[str] = []
    for project_name in sorted(grouped):
        if lines:
            lines.append("")
        lines.append(f"**{project_name}**")
        lines.extend(grouped[project_name][:4])
    return lines


def _build_auto_watch_lines(
    posts: list[dict],
    tag_details_by_post: dict[int, list[dict[str, str]]],
    judged_by_post: dict[int, dict],
    limit: int = 4,
) -> list[str]:
    lines: list[str] = []
    for post in posts:
        post_id = int(post.get("id") or 0)
        primary_tag = _highest_priority_tag(tag_details_by_post.get(post_id, []))
        judged = _judged(post_id, judged_by_post)
        if primary_tag in {"strong", "try_in_project", "interesting", "funny", "low_signal"}:
            continue
        if judged.get("include") is not True:
            continue
        if str(judged.get("category") or "") not in {"strong", "try_in_project", "interesting"}:
            continue
        lines.append(
            _render_signal(
                post,
                title=str(judged.get("title") or ""),
                key_takeaway=str(judged.get("key_takeaway") or ""),
                why_now=str(judged.get("why_now") or ""),
                project_application=str(judged.get("project_application") or ""),
            )
        )
        if len(lines) >= limit:
            break
    return lines or ["No additional high-confidence auto-selected signals this week."]


def format_signal_report(posts: list[dict], settings=None, *, reader_mode: bool = False) -> str:
    if not reader_mode:
        return _format_legacy_signal_report(posts, settings)

    db_path = str(getattr(settings, "db_path", "") or "").strip() if settings is not None else ""
    if not _table_exists(db_path, "user_post_tags"):
        return _format_legacy_signal_report(posts, settings)

    indexed_posts = [{**post, "_original_position": index} for index, post in enumerate(posts)]
    profile = _load_profile()
    ranked_posts = apply_personalization(indexed_posts, profile) if profile is not None else list(indexed_posts)
    tag_details_by_post = _load_user_tag_details([int(post.get("id") or 0) for post in ranked_posts], settings)
    projects = _load_projects()
    judged_by_post = judge_recent_posts(db_path, projects, lookback_days=21) if db_path else {}
    ranked_posts = _sort_posts_for_brief(ranked_posts, tag_details_by_post)

    visible_posts = [
        post
        for post in ranked_posts
        if _highest_priority_tag(tag_details_by_post.get(int(post.get("id") or 0), [])) != "low_signal"
    ]
    bucket_counts = Counter((post.get("bucket") or "noise") for post in posts)

    manual_sections = _build_manual_sections(visible_posts, tag_details_by_post, judged_by_post)
    project_lines = _build_project_sections(visible_posts, projects, tag_details_by_post, judged_by_post)
    auto_watch_lines = _build_auto_watch_lines(visible_posts, tag_details_by_post, judged_by_post)
    what_changed_lines = _build_what_changed_lines(bucket_counts)

    sections: list[str] = []
    for heading, lines in manual_sections:
        sections.extend([f"## {heading}", *lines, ""])

    sections.extend(
        [
            "## Project Insights",
            *project_lines,
            "",
            "## Additional Signals",
            *auto_watch_lines,
            "",
            "## What Changed",
            *what_changed_lines,
        ]
    )

    return "\n".join(line for line in sections if line is not None).strip() + "\n"
