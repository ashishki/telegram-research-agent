import logging
import re
import sqlite3
from datetime import datetime

from config.settings import Settings


LOGGER = logging.getLogger(__name__)
BATCH_SIZE = 500
FORWARD_HEADER_RE = re.compile(r"^\s*Forwarded from .+(?:\n+|$)", re.IGNORECASE)
BLANK_LINES_RE = re.compile(r"\n\s*\n+")
URL_RE = re.compile(r"https?://")
INDENTED_CODE_RE = re.compile(r"(?m)^(?: {4}|\t).+")
CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
LATIN_RE = re.compile(r"[A-Za-z]")


def _clean_content(text: str | None) -> str:
    content = (text or "").strip()
    content = FORWARD_HEADER_RE.sub("", content).strip()
    content = BLANK_LINES_RE.sub("\n\n", content)
    return content.strip()


def _extract_metadata(content: str) -> tuple[int, int, int]:
    url_count = len(URL_RE.findall(content))
    has_code = int("```" in content or INDENTED_CODE_RE.search(content) is not None)
    word_count = len(content.split())
    return url_count, has_code, word_count


def _detect_language(content: str) -> str:
    cyrillic_count = len(CYRILLIC_RE.findall(content))
    latin_count = len(LATIN_RE.findall(content))
    alpha_count = cyrillic_count + latin_count

    if alpha_count == 0:
        return "unknown"
    if cyrillic_count / alpha_count > 0.30:
        return "ru"
    if latin_count / alpha_count > 0.70:
        return "en"
    return "mixed"


def _fetch_unprocessed_batch(cursor: sqlite3.Cursor) -> list[sqlite3.Row]:
    cursor.execute(
        """
        SELECT
            raw_posts.id,
            raw_posts.channel_username,
            raw_posts.posted_at,
            raw_posts.text,
            raw_posts.media_caption
        FROM raw_posts
        LEFT JOIN posts ON posts.raw_post_id = raw_posts.id
        WHERE posts.raw_post_id IS NULL
        ORDER BY raw_posts.id
        LIMIT ?
        """,
        (BATCH_SIZE,),
    )
    return cursor.fetchall()


def run_normalization(settings: Settings) -> dict:
    totals = {"processed": 0, "skipped": 0, "errors": 0}

    with sqlite3.connect(settings.db_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        connection.execute("PRAGMA journal_mode = WAL;")

        read_cursor = connection.cursor()

        while True:
            rows = _fetch_unprocessed_batch(read_cursor)
            if not rows:
                continue

            batch_records: list[tuple[object, ...]] = []
            for row in rows:
                source_text = row["text"] or row["media_caption"] or ""
                content = _clean_content(source_text)

                url_count, has_code, word_count = _extract_metadata(content)
                batch_records.append(
                    (
                        row["id"],
                        row["channel_username"],
                        row["posted_at"],
                        content,
                        url_count,
                        has_code,
                        _detect_language(content),
                        word_count,
                        f"{datetime.utcnow().isoformat()}Z",
                    )
                )

            if not batch_records:
                LOGGER.info("Normalization batch had no insertable rows")
                continue

            try:
                connection.execute("BEGIN")
                connection.executemany(
                    """
                    INSERT INTO posts (
                        raw_post_id,
                        channel_username,
                        posted_at,
                        content,
                        url_count,
                        has_code,
                        language_detected,
                        word_count,
                        normalized_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    batch_records,
                )
                connection.commit()
                totals["processed"] += len(batch_records)
                # posts_fts stays in sync via the INSERT/UPDATE/DELETE triggers defined in schema.sql.
                LOGGER.info("Normalized batch processed=%d skipped=%d", len(batch_records), totals["skipped"])
            except Exception:
                connection.rollback()
                totals["errors"] += len(batch_records)
                LOGGER.exception("Normalization batch failed for %d rows", len(batch_records))
                continue

    LOGGER.info(
        "Normalization summary processed=%d skipped=%d errors=%d",
        totals["processed"],
        totals["skipped"],
        totals["errors"],
    )
    return totals
