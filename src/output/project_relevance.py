import re


_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "etc",
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


def _tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"\b[a-z]{3,}\b", text.lower())
        if token not in _STOPWORDS
    }


def score_project_relevance(post_content: str, projects: list[dict]) -> list[dict]:
    post_keywords = _tokenize(post_content or "")
    results: list[dict] = []

    for project in projects:
        name = str(project.get("name") or "")
        description = str(project.get("description") or "")
        focus = str(project.get("focus") or "")
        project_keywords = _tokenize(f"{description} {focus}")
        overlap_keywords = sorted(post_keywords & project_keywords)
        score = min(len(overlap_keywords) / max(len(project_keywords), 1), 1.0)

        if score > 0:
            rationale = f"Matches: {', '.join(overlap_keywords[:3])}"
        else:
            rationale = "No keyword overlap"

        results.append(
            {
                "name": name,
                "score": score,
                "rationale": rationale,
            }
        )

    return sorted(results, key=lambda item: item["score"], reverse=True)
