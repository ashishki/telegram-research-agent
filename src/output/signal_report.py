import json
import logging
import re
from collections import Counter
from pathlib import Path

import yaml

from output.personalize import apply_personalization
from output.project_relevance import score_project_relevance


LOGGER = logging.getLogger(__name__)
PROJECTS_YAML_PATH = Path(__file__).resolve().parents[1] / "config" / "projects.yaml"
PROFILE_YAML_PATH = Path(__file__).resolve().parents[1] / "config" / "profile.yaml"

_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "with",
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


def _parse_score_breakdown(value: str | None) -> dict:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _extract_topics_from_breakdown(score_breakdown: dict) -> list[str]:
    for key in ("topics", "topic_labels"):
        value = score_breakdown.get(key)
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, dict):
            return [str(item).strip() for item in value.keys() if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
    topic = score_breakdown.get("topic")
    if isinstance(topic, str) and topic.strip():
        return [topic.strip()]
    return []


def _derive_noise_topics(posts: list[dict]) -> str:
    collected_topics: list[str] = []
    for post in posts:
        score_breakdown = _parse_score_breakdown(post.get("score_breakdown"))
        collected_topics.extend(_extract_topics_from_breakdown(score_breakdown))

    if collected_topics:
        top_topics = [topic for topic, _ in Counter(collected_topics).most_common(3)]
        return ", ".join(top_topics)

    keywords: Counter[str] = Counter()
    for post in posts:
        for word in re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}", post.get("content", "").lower()):
            if word not in _STOPWORDS:
                keywords[word] += 1

    if not keywords:
        return "N/A"

    return ", ".join(word for word, _ in keywords.most_common(3))


def format_signal_report(posts: list[dict], settings) -> str:
    indexed_posts = [
        {
            **post,
            "_original_position": index,
        }
        for index, post in enumerate(posts)
    ]
    original_sorted_posts = sorted(
        indexed_posts,
        key=lambda post: float(post.get("signal_score") or 0.0),
        reverse=True,
    )
    original_rank_by_id = {
        post.get("_original_position"): rank for rank, post in enumerate(original_sorted_posts)
    }

    profile = _load_profile()
    ranked_posts = apply_personalization(indexed_posts, profile) if profile is not None else list(original_sorted_posts)
    personalized_rank_by_id = {
        post.get("_original_position"): rank for rank, post in enumerate(ranked_posts)
    }

    strong_posts = [post for post in ranked_posts if post.get("bucket") == "strong"]
    watch_posts = [post for post in ranked_posts if post.get("bucket") == "watch"]
    cultural_posts = [post for post in ranked_posts if post.get("bucket") == "cultural"]
    noise_posts = [post for post in ranked_posts if post.get("bucket") == "noise"]

    strong_lines = [
        f"- [score={float(post.get('signal_score') or 0.0):.2f}] "
        f"[model={post.get('routed_model') or 'unknown'}] "
        f"{'[personalized] ' if original_rank_by_id.get(post.get('_original_position')) != personalized_rank_by_id.get(post.get('_original_position')) else ''}"
        f"{_truncate_words(post.get('content'), 20)}"
        for post in strong_posts
    ]
    watch_lines = [
        f"- [score={float(post.get('signal_score') or 0.0):.2f}] "
        f"{'[personalized] ' if original_rank_by_id.get(post.get('_original_position')) != personalized_rank_by_id.get(post.get('_original_position')) else ''}"
        f"{_truncate_words(post.get('content'), 20)}"
        for post in watch_posts
    ]
    cultural_lines = [
        f"- {_truncate_words(post.get('content'), 15)}"
        for post in cultural_posts
    ]

    bucket_counts = Counter((post.get("bucket") or "noise") for post in posts)
    stats_lines = [
        f"Total posts: {len(posts)}",
        (
            "Bucket breakdown: "
            f"strong={bucket_counts.get('strong', 0)}, "
            f"watch={bucket_counts.get('watch', 0)}, "
            f"cultural={bucket_counts.get('cultural', 0)}, "
            f"noise={bucket_counts.get('noise', 0)}"
        ),
    ]

    project_relevance_lines: list[str] = []
    projects = _load_projects()
    if projects is not None:
        for post in strong_posts + watch_posts:
            matches = score_project_relevance(post.get("content", ""), projects)
            for match in matches:
                if float(match.get("score") or 0.0) < 0.3:
                    continue
                project_relevance_lines.append(
                    f"- [{match.get('name')}] (score={float(match.get('score') or 0.0):.2f}): "
                    f"{match.get('rationale')} — {_truncate_words(post.get('content'), 10)}"
                )
        if not project_relevance_lines:
            project_relevance_lines.append("No project matches above threshold.")

    sections = [
        "## Strong Signals",
        *strong_lines,
        "",
        "## Watch",
        *watch_lines,
        "",
        "## Cultural",
        *cultural_lines,
        "",
        "## Ignored",
        f"{len(noise_posts)} posts filtered as noise. Top topics: {_derive_noise_topics(noise_posts)}",
        "",
        "## Think Layer",
        "Themes and patterns will be synthesized here.",
        "",
        "## Stats",
        *stats_lines,
    ]
    if projects is not None:
        sections.extend(
            [
                "",
                "## Project Relevance",
                *project_relevance_lines,
            ]
        )
    return "\n".join(sections).strip() + "\n"
