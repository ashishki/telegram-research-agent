import json
import re
from collections import Counter


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
    strong_posts = sorted(
        [post for post in posts if post.get("bucket") == "strong"],
        key=lambda post: float(post.get("signal_score") or 0.0),
        reverse=True,
    )
    watch_posts = sorted(
        [post for post in posts if post.get("bucket") == "watch"],
        key=lambda post: float(post.get("signal_score") or 0.0),
        reverse=True,
    )
    cultural_posts = [post for post in posts if post.get("bucket") == "cultural"]
    noise_posts = [post for post in posts if post.get("bucket") == "noise"]

    strong_lines = [
        f"- [score={float(post.get('signal_score') or 0.0):.2f}] "
        f"[model={post.get('routed_model') or 'unknown'}] "
        f"{_truncate_words(post.get('content'), 20)}"
        for post in strong_posts
    ]
    watch_lines = [
        f"- [score={float(post.get('signal_score') or 0.0):.2f}] "
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
    return "\n".join(sections).strip() + "\n"
