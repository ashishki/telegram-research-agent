import json
import logging
import re
import sqlite3
from datetime import datetime
from typing import Any

from config.settings import PROJECT_ROOT, Settings
from llm.client import LLMError, LLMSchemaError, complete_json
from processing.cluster import cluster_posts


LOGGER = logging.getLogger(__name__)
PROMPT_PATH = PROJECT_ROOT / "docs" / "prompts" / "rubric_discovery.md"
TOKEN_RE = re.compile(r"[a-z0-9]+")
OVERLAP_THRESHOLD = 3
MERGE_CONFIDENCE = 0.7
NEW_TOPIC_CONFIDENCE_MIN = 0.5


def _utc_now_iso() -> str:
    return f"{datetime.utcnow().isoformat()}Z"


def _tokenize(text: str | None) -> set[str]:
    return set(TOKEN_RE.findall((text or "").lower()))


def _extract_markdown_section(text: str, heading: str) -> str:
    pattern = re.compile(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)
    match = pattern.search(text)
    if not match:
        raise ValueError(f"Section not found in prompt file: {heading}")
    return match.group(1).strip()


def _load_prompt_sections() -> tuple[str, str]:
    prompt_markdown = PROMPT_PATH.read_text(encoding="utf-8")
    system_prompt = _extract_markdown_section(prompt_markdown, "System Prompt")
    user_template = _extract_markdown_section(prompt_markdown, "User Prompt Template")
    return system_prompt, user_template


def _load_existing_topics(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT id, label, description
        FROM topics
        ORDER BY id ASC
        """
    ).fetchall()
    topics: list[dict[str, Any]] = []
    for row in rows:
        combined_text = f"{row['label'] or ''} {row['description'] or ''}"
        topics.append(
            {
                "id": row["id"],
                "label": row["label"],
                "description": row["description"] or "",
                "tokens": _tokenize(combined_text),
            }
        )
    return topics


def _find_overlap_topic(cluster_keywords: list[str], existing_topics: list[dict[str, Any]]) -> dict[str, Any] | None:
    keyword_set = {keyword.lower() for keyword in cluster_keywords}
    best_match: dict[str, Any] | None = None
    best_overlap = 0

    for topic in existing_topics:
        overlap = len(keyword_set & topic["tokens"])
        if overlap >= OVERLAP_THRESHOLD and overlap > best_overlap:
            best_match = topic
            best_overlap = overlap

    return best_match


def _fetch_cluster_excerpts(connection: sqlite3.Connection, post_ids: list[int]) -> list[str]:
    if not post_ids:
        return []

    placeholders = ", ".join("?" for _ in post_ids)
    rows = connection.execute(
        f"""
        SELECT id, content
        FROM posts
        WHERE id IN ({placeholders})
        ORDER BY posted_at ASC, id ASC
        LIMIT 3
        """,
        post_ids,
    ).fetchall()
    return [(row["content"] or "")[:200] for row in rows]


def _assign_posts_to_topic(
    connection: sqlite3.Connection,
    topic_id: int,
    post_ids: list[int],
    confidence: float,
    now_iso: str,
) -> None:
    connection.executemany(
        """
        INSERT OR IGNORE INTO post_topics (post_id, topic_id, confidence)
        VALUES (?, ?, ?)
        """,
        [(post_id, topic_id, confidence) for post_id in post_ids],
    )
    connection.execute(
        """
        UPDATE topics
        SET last_seen = ?,
            post_count = (
                SELECT COUNT(*)
                FROM post_topics
                WHERE topic_id = topics.id
            )
        WHERE id = ?
        """,
        (now_iso, topic_id),
    )


def _render_user_prompt(
    user_template: str,
    top_keywords: list[str],
    sample_excerpts: list[str],
    existing_topics: list[str],
) -> str:
    return (
        user_template.replace("{top_keywords}", json.dumps(top_keywords))
        .replace("{sample_excerpts}", json.dumps(sample_excerpts))
        .replace("{existing_topics}", json.dumps(existing_topics))
    )


def _coerce_response(response: dict[str, Any]) -> dict[str, Any]:
    label = str(response.get("label", "")).strip()
    description = str(response.get("description", "")).strip()
    is_new = bool(response.get("is_new"))
    merged_into = response.get("merged_into")
    if merged_into is not None:
        merged_into = str(merged_into).strip()

    try:
        confidence = float(response.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    return {
        "label": label,
        "description": description,
        "is_new": is_new,
        "merged_into": merged_into,
        "confidence": confidence,
    }


def run_topic_detection(settings: Settings) -> dict:
    result = {"new_topics": 0, "merged": 0, "skipped": 0}
    clusters = cluster_posts(settings)
    if not clusters:
        LOGGER.info("Topic detection skipped: no clusters available")
        return result

    system_prompt, user_template = _load_prompt_sections()

    with sqlite3.connect(settings.db_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        connection.execute("PRAGMA journal_mode = WAL;")

        existing_topics = _load_existing_topics(connection)
        topic_lookup = {topic["label"]: topic for topic in existing_topics}

        for cluster in clusters:
            cluster_id = cluster["cluster_id"]
            post_ids = cluster["post_ids"]
            top_keywords = cluster["top_keywords"]
            now_iso = _utc_now_iso()

            overlap_topic = _find_overlap_topic(top_keywords, existing_topics)
            if overlap_topic is not None:
                try:
                    connection.execute("BEGIN")
                    _assign_posts_to_topic(connection, overlap_topic["id"], post_ids, MERGE_CONFIDENCE, now_iso)
                    connection.commit()
                    result["merged"] += 1
                    LOGGER.info(
                        "Merged cluster_id=%d into topic=%r via keyword overlap",
                        cluster_id,
                        overlap_topic["label"],
                    )
                except Exception:
                    connection.rollback()
                    result["skipped"] += 1
                    LOGGER.exception("Failed to persist overlap merge for cluster_id=%d", cluster_id)
                continue

            excerpts = _fetch_cluster_excerpts(connection, post_ids)
            prompt = _render_user_prompt(
                user_template=user_template,
                top_keywords=top_keywords,
                sample_excerpts=excerpts,
                existing_topics=[topic["label"] for topic in existing_topics],
            )

            try:
                llm_response = _coerce_response(complete_json(prompt=prompt, system=system_prompt))
            except (LLMError, LLMSchemaError):
                result["skipped"] += 1
                LOGGER.exception("LLM topic labeling failed for cluster_id=%d", cluster_id)
                continue

            if llm_response["merged_into"]:
                merged_topic = topic_lookup.get(llm_response["merged_into"])
                if merged_topic is None:
                    result["skipped"] += 1
                    LOGGER.warning(
                        "Skipping cluster_id=%d: LLM returned unknown merged_into=%r",
                        cluster_id,
                        llm_response["merged_into"],
                    )
                    continue

                try:
                    connection.execute("BEGIN")
                    _assign_posts_to_topic(connection, merged_topic["id"], post_ids, MERGE_CONFIDENCE, now_iso)
                    connection.commit()
                    result["merged"] += 1
                    LOGGER.info(
                        "Merged cluster_id=%d into topic=%r via LLM decision",
                        cluster_id,
                        merged_topic["label"],
                    )
                except Exception:
                    connection.rollback()
                    result["skipped"] += 1
                    LOGGER.exception("Failed to persist LLM merge for cluster_id=%d", cluster_id)
                continue

            if not llm_response["is_new"] or llm_response["confidence"] < NEW_TOPIC_CONFIDENCE_MIN:
                result["skipped"] += 1
                LOGGER.info(
                    "Skipping cluster_id=%d due to low-confidence new topic response confidence=%.2f",
                    cluster_id,
                    llm_response["confidence"],
                )
                continue

            if not llm_response["label"]:
                result["skipped"] += 1
                LOGGER.warning("Skipping cluster_id=%d: LLM returned empty label", cluster_id)
                continue

            existing_label_topic = topic_lookup.get(llm_response["label"])
            if existing_label_topic is not None:
                try:
                    connection.execute("BEGIN")
                    _assign_posts_to_topic(connection, existing_label_topic["id"], post_ids, MERGE_CONFIDENCE, now_iso)
                    connection.commit()
                    result["merged"] += 1
                    LOGGER.info(
                        "Merged cluster_id=%d into existing topic=%r after LLM returned a duplicate label",
                        cluster_id,
                        existing_label_topic["label"],
                    )
                except Exception:
                    connection.rollback()
                    result["skipped"] += 1
                    LOGGER.exception("Failed to persist duplicate-label merge for cluster_id=%d", cluster_id)
                continue

            try:
                connection.execute("BEGIN")
                cursor = connection.execute(
                    """
                    INSERT INTO topics (label, description, first_seen, last_seen, post_count)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        llm_response["label"],
                        llm_response["description"],
                        now_iso,
                        now_iso,
                        len(post_ids),
                    ),
                )
                topic_id = cursor.lastrowid
                _assign_posts_to_topic(connection, topic_id, post_ids, llm_response["confidence"], now_iso)
                connection.commit()

                new_topic = {
                    "id": topic_id,
                    "label": llm_response["label"],
                    "description": llm_response["description"],
                    "tokens": _tokenize(f"{llm_response['label']} {llm_response['description']}"),
                }
                existing_topics.append(new_topic)
                topic_lookup[new_topic["label"]] = new_topic
                result["new_topics"] += 1
                LOGGER.info(
                    "Created new topic=%r from cluster_id=%d confidence=%.2f",
                    llm_response["label"],
                    cluster_id,
                    llm_response["confidence"],
                )
            except Exception:
                connection.rollback()
                result["skipped"] += 1
                LOGGER.exception("Failed to persist new topic for cluster_id=%d", cluster_id)

    LOGGER.info(
        "Topic detection summary new_topics=%d merged=%d skipped=%d",
        result["new_topics"],
        result["merged"],
        result["skipped"],
    )
    return result
