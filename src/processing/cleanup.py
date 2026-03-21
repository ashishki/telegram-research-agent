"""
Database cleanup: strips raw_json after normalization and deletes posts older than
RETAIN_DAYS. Always run AFTER digest/insight generation to preserve the full
90-day lookback window during report generation.
"""
import logging
import sqlite3
from datetime import datetime, timedelta, timezone


LOGGER = logging.getLogger(__name__)
RETAIN_DAYS = 100  # safe buffer above the 90-day insight lookback


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def run_cleanup(db_path: str, retain_days: int = RETAIN_DAYS) -> dict:
    cutoff_iso = (_utc_now() - timedelta(days=retain_days)).isoformat().replace("+00:00", "Z")
    totals = {"raw_json_nulled": 0, "posts_deleted": 0, "vacuum": False}

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON;")
        connection.execute("PRAGMA journal_mode = WAL;")

        # 1. Strip raw_json for posts that have already been normalized — it's
        #    a full JSON copy of every other column and accounts for ~54% of DB size.
        connection.execute("BEGIN")
        cursor = connection.execute(
            """
            UPDATE raw_posts
            SET raw_json = ''
            WHERE raw_json != ''
              AND id IN (SELECT raw_post_id FROM posts)
            """
        )
        totals["raw_json_nulled"] = cursor.rowcount
        connection.commit()
        LOGGER.info("Cleanup step=strip_raw_json nulled=%d", totals["raw_json_nulled"])

        # 2. Delete raw_posts older than retain_days. FK CASCADE removes the
        #    linked rows in posts, post_topics, post_project_links, and posts_fts.
        connection.execute("BEGIN")
        cursor = connection.execute(
            "DELETE FROM raw_posts WHERE posted_at < ?",
            (cutoff_iso,),
        )
        totals["posts_deleted"] = cursor.rowcount
        connection.commit()
        LOGGER.info(
            "Cleanup step=delete_old_posts deleted=%d cutoff=%s",
            totals["posts_deleted"],
            cutoff_iso,
        )

    # 3. VACUUM outside the WAL transaction to reclaim freed pages.
    if totals["raw_json_nulled"] > 0 or totals["posts_deleted"] > 0:
        with sqlite3.connect(db_path) as connection:
            connection.execute("VACUUM")
        totals["vacuum"] = True
        LOGGER.info("Cleanup step=vacuum done")

    LOGGER.info(
        "Cleanup summary raw_json_nulled=%d posts_deleted=%d vacuum=%s",
        totals["raw_json_nulled"],
        totals["posts_deleted"],
        totals["vacuum"],
    )
    return totals
