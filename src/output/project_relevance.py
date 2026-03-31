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


def _get_project_keywords(project: dict) -> list[str]:
    """Return explicit keyword list or fall back to tokenizing focus string."""
    keywords = project.get("keywords")
    if isinstance(keywords, list) and keywords:
        return [str(k).strip().lower() for k in keywords if str(k).strip()]
    focus = str(project.get("focus") or "")
    description = str(project.get("description") or "")
    return list(_tokenize(f"{description} {focus}"))


def score_project_relevance(post_content: str, projects: list[dict]) -> list[dict]:
    post_tokens = _tokenize(post_content or "")
    results: list[dict] = []

    for project in projects:
        name = str(project.get("name") or "")
        project_keywords = _get_project_keywords(project)
        project_token_set = set(project_keywords)

        overlap_keywords = sorted(post_tokens & project_token_set)
        score = min(len(overlap_keywords) / max(len(project_token_set), 1), 1.0)

        if overlap_keywords:
            rationale = f"Matches: {', '.join(overlap_keywords[:3])}"
        else:
            rationale = "No keyword overlap"

        # Apply exclude_keywords suppression
        exclude_keywords = project.get("exclude_keywords")
        if isinstance(exclude_keywords, list) and exclude_keywords and overlap_keywords:
            for excl in exclude_keywords:
                excl_token = str(excl).strip().lower()
                if excl_token and excl_token in post_tokens:
                    score = 0.05
                    rationale = f"{rationale}; excluded: {excl_token}"
                    break

        results.append(
            {
                "name": name,
                "score": score,
                "rationale": rationale,
            }
        )

    return sorted(results, key=lambda item: item["score"], reverse=True)
