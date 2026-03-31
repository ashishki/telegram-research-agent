from collections import Counter

from output.project_relevance import _tokenize


def extract_learning_gaps(posts: list[dict], projects: list[dict]) -> list[dict]:
    relevant_posts = [
        post for post in posts
        if post.get("bucket") in {"strong", "watch"}
    ]

    keyword_counts: Counter[str] = Counter()
    for post in relevant_posts:
        keyword_counts.update(_tokenize(str(post.get("content") or "")))

    covered_keywords: set[str] = set()
    for project in projects:
        description = str(project.get("description") or "")
        focus = str(project.get("focus") or "")
        covered_keywords.update(_tokenize(f"{description} {focus}"))

    gaps = [
        {
            "topic": topic,
            "frequency": frequency,
            "rationale": f"Appeared {frequency} times in strong/watch posts, not in any project focus",
            "linked_project": None,
        }
        for topic, frequency in keyword_counts.most_common()
        if frequency >= 2 and topic not in covered_keywords
    ]
    return gaps[:5]
