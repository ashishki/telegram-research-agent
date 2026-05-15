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


def _keyword_matches_content(keyword: str, content_lower: str, post_tokens: set[str]) -> tuple[bool, list[str]]:
    keyword_lower = keyword.strip().lower()
    if not keyword_lower:
        return False, []

    if len(keyword_lower) < 3 and keyword_lower.isalnum():
        boundary_pattern = rf"(?<![a-z0-9]){re.escape(keyword_lower)}(?![a-z0-9])"
        if re.search(boundary_pattern, content_lower):
            return True, [keyword_lower]
    elif keyword_lower in content_lower:
        return True, [keyword_lower]

    keyword_tokens = _tokenize(keyword_lower)
    matched_tokens = sorted(keyword_tokens & post_tokens)
    return bool(matched_tokens), matched_tokens


def _score_keyword_overlap(matched_count: int, keyword_count: int) -> float:
    denominator = max(1, min(keyword_count, 4))
    return min(matched_count / denominator, 1.0)


def score_project_relevance(post_content: str, projects: list[dict]) -> list[dict]:
    content_lower = (post_content or "").lower()
    post_tokens = _tokenize(post_content or "")
    results: list[dict] = []

    for project in projects:
        name = str(project.get("name") or "")
        project_keywords = _get_project_keywords(project)
        matched_keyword_labels: list[str] = []
        matched_terms: set[str] = set()
        for keyword in project_keywords:
            matched, terms = _keyword_matches_content(keyword, content_lower, post_tokens)
            if matched:
                matched_keyword_labels.append(keyword)
                matched_terms.update(terms)

        score = _score_keyword_overlap(len(matched_keyword_labels), len(project_keywords))
        overlap_keywords = sorted(matched_terms or set(matched_keyword_labels))

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
