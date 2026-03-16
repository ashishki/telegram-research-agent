import json
import logging
import sqlite3


LOGGER = logging.getLogger(__name__)
NO_OVERLAP_NOTE = "active this week, no Telegram overlap found"


def _load_topics(connection: sqlite3.Connection) -> list[tuple[str, str]]:
    rows = connection.execute(
        """
        SELECT label, description
        FROM topics
        ORDER BY label ASC
        """
    ).fetchall()
    return [(str(row["label"] or ""), str(row["description"] or "")) for row in rows]


def _parse_keywords_blob(value: str) -> list[str]:
    if not value:
        return []
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return [value]
    if not isinstance(decoded, list):
        return []
    return [str(item) for item in decoded if str(item).strip()]


def crossref_repos_to_topics(repos: list[dict], db_path: str) -> dict[str, list[str]]:
    matches: dict[str, list[str]] = {}

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        topics = _load_topics(connection)

    for repo in repos:
        repo_name = str(repo.get("name") or "").strip()
        if not repo_name:
            continue

        repo_terms = {
            term.lower()
            for term in repo.get("languages", []) + repo.get("topics", []) + repo.get("keywords_list", [])
            if str(term).strip()
        }
        matched_labels: list[str] = []

        for label, description in topics:
            label_lower = label.lower()
            description_lower = description.lower()
            overlap_score = 0

            for term in repo_terms:
                if term in label_lower or term in description_lower:
                    overlap_score += 1

            description_keywords = _parse_keywords_blob(description)
            for keyword in description_keywords:
                keyword_lower = keyword.lower()
                for term in repo_terms:
                    if term in keyword_lower:
                        overlap_score += 1

            if overlap_score > 0:
                matched_labels.append(label)

        if matched_labels:
            matches[repo_name] = matched_labels
        elif int(repo.get("weekly_commits") or 0) > 0:
            matches[repo_name] = [NO_OVERLAP_NOTE]

    LOGGER.info("GitHub cross-reference complete repos_with_matches=%d", len(matches))
    return matches
