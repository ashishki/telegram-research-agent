import json
import logging
import os
import re
import sqlite3
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

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
URL_RE = re.compile(r"https?://[^\s<>)]+", re.IGNORECASE)
PRIMARY_SOURCE_DOMAINS = {
    "anthropic.com",
    "openai.com",
    "ai.google",
    "deepmind.google",
    "microsoft.com",
    "nvidia.com",
    "github.com",
    "arxiv.org",
}
MACRO_SIGNAL_KEYWORDS = {
    "compute",
    "chips",
    "chip",
    "export controls",
    "infrastructure",
    "ai leadership",
    "frontier ai",
    "dual-use",
    "2028",
    "китай",
    "сша",
    "чип",
    "чипы",
    "инфраструктур",
    "экспортн",
    "прогноз",
    "лидерств",
    "двойного назначения",
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


def _domain_from_url(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


def _extract_external_urls(text: str | None) -> list[str]:
    urls: list[str] = []
    for match in URL_RE.finditer(text or ""):
        url = match.group(0).rstrip(".,;:")
        domain = _domain_from_url(url)
        if not domain or domain == "t.me":
            continue
        urls.append(url)
    return urls


def _source_tier(url: str) -> str:
    domain = _domain_from_url(url)
    if not domain:
        return ""
    for primary in PRIMARY_SOURCE_DOMAINS:
        if domain == primary or domain.endswith(f".{primary}"):
            return "primary"
    return "external"


def _primary_source_url(post: dict) -> str:
    for url in _extract_external_urls(post.get("content")):
        if _source_tier(url) == "primary":
            return url
    return ""


def _is_macro_signal(post: dict) -> bool:
    text = (post.get("content") or "").lower()
    return any(keyword in text for keyword in MACRO_SIGNAL_KEYWORDS)


def _load_previous_quality_metrics(db_path: str = "") -> dict | None:
    if not db_path:
        db_path = os.environ.get("AGENT_DB_PATH", "").strip()
    if not db_path:
        return None
    try:
        with sqlite3.connect(db_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """
                SELECT total_posts, strong_count, watch_count, noise_count, avg_signal_score
                FROM quality_metrics
                ORDER BY computed_at DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
    except sqlite3.Error:
        LOGGER.warning("Failed to load previous quality metrics from %s", db_path, exc_info=True)
        return None
    return dict(row) if row is not None else None


def _build_source_analytics_lines(posts: list[dict]) -> list[str]:
    """Top signal sources: channels that contributed strong/watch posts this week."""
    channel_stats: dict[str, dict] = {}
    for post in posts:
        ch = (post.get("channel_username") or "").strip()
        if not ch:
            continue
        if ch not in channel_stats:
            channel_stats[ch] = {"signal": 0, "total": 0, "score_sum": 0.0}
        channel_stats[ch]["total"] += 1
        bucket = post.get("bucket") or "noise"
        score = float(post.get("signal_score") or 0.0)
        channel_stats[ch]["score_sum"] += score
        if bucket in ("strong", "watch"):
            channel_stats[ch]["signal"] += 1

    ranked = sorted(
        channel_stats.items(),
        key=lambda kv: (-kv[1]["signal"], -kv[1]["score_sum"]),
    )
    top = [(ch, s) for ch, s in ranked if s["signal"] > 0][:5]

    if not top:
        return ["No signal sources this week."]

    lines = []
    for ch, s in top:
        avg = s["score_sum"] / s["total"] if s["total"] else 0.0
        lines.append(f"- {ch}: {s['signal']} signal posts, avg score {avg:.2f}")
    return lines


def _build_what_changed_lines(bucket_counts: Counter, db_path: str = "") -> list[str]:
    previous = _load_previous_quality_metrics(db_path=db_path)
    if previous is None:
        return ["No comparison baseline available."]

    lines = []
    for bucket_name in ("strong", "watch", "noise"):
        current = int(bucket_counts.get(bucket_name, 0))
        prior = int(previous.get(f"{bucket_name}_count") or 0)
        delta = current - prior
        lines.append(f"- {bucket_name}: {current} (was {prior}, {delta:+d})")
    return lines


def _summarize_signal_change(bucket_counts: Counter, db_path: str = "") -> str:
    previous = _load_previous_quality_metrics(db_path=db_path)
    if previous is None:
        return "No comparison baseline available."
    parts: list[str] = []
    for bucket_name in ("watch", "noise"):
        current = int(bucket_counts.get(bucket_name, 0))
        prior = int(previous.get(f"{bucket_name}_count") or 0)
        parts.append(f"{bucket_name} {prior} -> {current}")
    return ", ".join(parts) + "."


def _build_action_lines(
    *,
    bucket_counts: Counter,
    manual_sections: list[tuple[str, list[str]]],
    project_lines: list[str],
    auto_watch_lines: list[str],
) -> list[str]:
    actions: list[str] = []
    if manual_sections:
        first_heading, first_lines = manual_sections[0]
        if first_lines:
            actions.append(f"Review {first_heading.lower()} and decide whether to apply the first item.")
    if project_lines and project_lines != ["No project-specific signals this week."]:
        actions.append("Use Project Insights to update the active repo/backlog that has the clearest source-backed signal.")
    if auto_watch_lines and auto_watch_lines != ["No additional high-confidence auto-selected signals this week."]:
        actions.append("Keep the additional high-confidence signals in view before turning them into work.")
    if not actions:
        actionable = int(bucket_counts.get("strong", 0)) + int(bucket_counts.get("watch", 0))
        if actionable <= 0:
            actions.append("Skip deep reading this week unless you are debugging ingestion or scoring quality.")
        else:
            actions.append("Scan the watch signals, but defer new work until evidence becomes more specific.")
    return [f"{index}. {action}" for index, action in enumerate(actions[:3], start=1)]


def _build_source_mix_summary(posts: list[dict]) -> str:
    signal_posts = [
        post
        for post in posts
        if str(post.get("bucket") or "noise") in {"strong", "watch"}
    ]
    if not signal_posts:
        return "Telegram-only scan; no strong/watch source concentration."
    channel_counts = Counter(
        str(post.get("channel_username") or "").strip()
        for post in signal_posts
        if str(post.get("channel_username") or "").strip()
    )
    top_channels = ", ".join(f"{channel} ({count})" for channel, count in channel_counts.most_common(3))
    linked_count = sum(1 for post in signal_posts if str(post.get("message_url") or "").strip())
    if not top_channels:
        return f"Telegram-only scan; {linked_count} linked source posts."
    return f"Telegram-only scan; top signal sources: {top_channels}; linked posts: {linked_count}."


def _build_evidence_confidence_line(posts: list[dict], bucket_counts: Counter) -> str:
    strong_count = int(bucket_counts.get("strong", 0))
    watch_count = int(bucket_counts.get("watch", 0))
    actionable_count = strong_count + watch_count
    linked_count = sum(
        1
        for post in posts
        if str(post.get("bucket") or "noise") in {"strong", "watch"}
        and str(post.get("message_url") or "").strip()
    )
    if actionable_count <= 0:
        return "Evidence: no strong/watch signals; confidence low."
    if strong_count > 0 and linked_count >= actionable_count:
        return f"Evidence: {linked_count} linked Telegram source posts; confidence medium."
    return f"Evidence: {linked_count} linked Telegram source posts for {actionable_count} strong/watch signals; confidence low-to-medium."


def _build_decision_brief_lines(
    *,
    posts: list[dict],
    bucket_counts: Counter,
    actions: list[str],
    db_path: str = "",
) -> list[str]:
    post_count = len(posts)
    strong_count = int(bucket_counts.get("strong", 0))
    watch_count = int(bucket_counts.get("watch", 0))
    cultural_count = int(bucket_counts.get("cultural", 0))
    noise_count = int(bucket_counts.get("noise", 0))
    actionable_count = strong_count + watch_count
    guidance = (
        "Read this if you are choosing project work this week."
        if actionable_count > 0
        else "Skip if you only need project decisions; read only to debug signal quality."
    )
    decision = actions[0].split(". ", maxsplit=1)[1] if actions else "No immediate action recommended."
    return [
        f"- Evaluated: {post_count} Telegram posts from the last 7 days.",
        (
            f"- Funnel: {post_count} posts -> {strong_count} strong / {watch_count} watch / "
            f"{cultural_count} cultural / {noise_count} noise -> {len(actions)} actions."
        ),
        f"- Signal change: {_summarize_signal_change(bucket_counts, db_path=db_path)}",
        f"- Decision: {decision}",
        f"- {_build_evidence_confidence_line(posts, bucket_counts)}",
        f"- Source mix: {_build_source_mix_summary(posts)}",
        f"- {guidance}",
    ]


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
        channel = (post.get("channel_username") or "").strip()
        if project_application.strip() and channel:
            lines.append(f"  Source: {channel} | {source}")
        else:
            lines.append(f"  Source: {source}")
    return "\n".join(lines)


def _build_macro_context_lines(
    posts: list[dict],
    judged_by_post: dict[int, dict],
    limit: int = 3,
) -> list[str]:
    lines: list[str] = []
    seen: set[int] = set()
    for post in posts:
        post_id = int(post.get("id") or 0)
        if post_id in seen:
            continue
        primary_url = _primary_source_url(post)
        if not _is_macro_signal(post):
            continue
        judged = _judged(post_id, judged_by_post)
        rendered = _render_signal(
            post,
            title=str(judged.get("title") or ""),
            key_takeaway=str(judged.get("key_takeaway") or ""),
            why_now=str(judged.get("why_now") or ""),
            project_application=str(judged.get("project_application") or ""),
        )
        if primary_url:
            rendered += f"\n  Primary source: {_source_tier(primary_url)} | {primary_url}"
        lines.append(rendered)
        seen.add(post_id)
        if len(lines) >= limit:
            break
    return lines


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
    db_path = str(getattr(settings, "db_path", "") or "").strip() if settings is not None else ""
    if not db_path:
        db_path = os.environ.get("AGENT_DB_PATH", "").strip()
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
            *_build_what_changed_lines(bucket_counts, db_path=db_path),
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
) -> tuple[list[str], set[int]]:
    if not projects:
        return ["No project-specific signals this week."], set()

    grouped: dict[str, list[str]] = {}
    used_post_ids: set[int] = set()
    for post in posts:
        post_id = int(post.get("id") or 0)
        primary_tag = _highest_priority_tag(tag_details_by_post.get(post_id, []))
        if primary_tag == "low_signal":
            continue
        judged = _judged(post_id, judged_by_post)
        judged_project = str(judged.get("project_name") or "").strip()
        if judged_project:
            used_post_ids.add(post_id)
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
            used_post_ids.add(post_id)
            project_name = str(match.get("name") or "unknown")
            rationale = str(match.get("rationale") or "").strip()
            note = _note_for_tag(tag_details_by_post.get(post_id, []), primary_tag or "")
            detail = rationale or note or "relevant pattern"
            grouped.setdefault(project_name, []).append(
                _render_signal(post, key_takeaway=detail)
            )

    if not grouped:
        return ["No project-specific signals this week."], set()

    lines: list[str] = []
    for project_name in sorted(grouped):
        if lines:
            lines.append("")
        lines.append(f"**{project_name}**")
        lines.extend(grouped[project_name][:4])
    return lines, used_post_ids


def _build_auto_watch_lines(
    posts: list[dict],
    tag_details_by_post: dict[int, list[dict[str, str]]],
    judged_by_post: dict[int, dict],
    excluded_post_ids: set[int] | None = None,
    limit: int = 4,
) -> list[str]:
    lines: list[str] = []
    excluded = excluded_post_ids or set()
    for post in posts:
        post_id = int(post.get("id") or 0)
        if post_id in excluded:
            continue
        primary_tag = _highest_priority_tag(tag_details_by_post.get(post_id, []))
        judged = _judged(post_id, judged_by_post)
        if primary_tag in {"strong", "try_in_project", "interesting", "funny", "low_signal"}:
            continue
        category = str(judged.get("category") or "")
        if category not in {"strong", "try_in_project", "interesting"}:
            continue
        confidence = float(judged.get("confidence") or 0.0)
        # Show if judge explicitly approved, OR if it has a strong category with decent confidence
        if not judged.get("include") and confidence < 0.65:
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
    project_lines, project_post_ids = _build_project_sections(visible_posts, projects, tag_details_by_post, judged_by_post)
    auto_watch_lines = _build_auto_watch_lines(
        visible_posts,
        tag_details_by_post,
        judged_by_post,
        excluded_post_ids=project_post_ids,
    )
    macro_context_lines = _build_macro_context_lines(visible_posts, judged_by_post)
    what_changed_lines = _build_what_changed_lines(bucket_counts, db_path=db_path)
    source_analytics_lines = _build_source_analytics_lines(posts)
    action_lines = _build_action_lines(
        bucket_counts=bucket_counts,
        manual_sections=manual_sections,
        project_lines=project_lines,
        auto_watch_lines=auto_watch_lines,
    )
    decision_brief_lines = _build_decision_brief_lines(
        posts=posts,
        bucket_counts=bucket_counts,
        actions=action_lines,
        db_path=db_path,
    )

    sections: list[str] = [
        "## Decision Brief",
        *decision_brief_lines,
        "",
        "## Actions This Week",
        *action_lines,
        "",
        "## What Changed",
        *what_changed_lines,
        "",
    ]
    for heading, lines in manual_sections:
        sections.extend([f"## {heading}", *lines, ""])

    if macro_context_lines:
        sections.extend(["## Macro Context", *macro_context_lines, ""])

    sections.extend([
        "## Project Insights",
        *project_lines,
        "",
        "## Additional Signals",
        *auto_watch_lines,
        "",
        "## Source Map",
        *source_analytics_lines,
    ])

    return "\n".join(line for line in sections if line is not None).strip() + "\n"
