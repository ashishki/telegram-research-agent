import logging
import os
import sqlite3
from pathlib import Path


LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = "data/agent.db"
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def get_db_path() -> Path:
    raw_path = os.environ.get("AGENT_DB_PATH", DEFAULT_DB_PATH)
    path = Path(raw_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def run_migrations() -> Path:
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    LOGGER.info("Running database migrations against %s", db_path)

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON;")
        connection.execute("PRAGMA journal_mode = WAL;")
        connection.executescript(schema_sql)
        for stmt in [
            "ALTER TABLE projects ADD COLUMN github_repo TEXT",
            "ALTER TABLE projects ADD COLUMN last_commit_at TEXT",
            "ALTER TABLE projects ADD COLUMN github_synced_at TEXT",
        ]:
            try:
                connection.execute(stmt)
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
        try:
            connection.execute("ALTER TABLE raw_posts ADD COLUMN message_url TEXT")
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise
        try:
            connection.execute("ALTER TABLE raw_posts ADD COLUMN image_description TEXT")
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise
        try:
            connection.execute("ALTER TABLE digests ADD COLUMN content_json TEXT")
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise
        try:
            connection.execute("ALTER TABLE digests ADD COLUMN pdf_path TEXT")
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS llm_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                called_at TEXT NOT NULL,
                category TEXT NOT NULL,
                model TEXT NOT NULL,
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                cost_usd REAL NOT NULL DEFAULT 0.0,
                duration_ms INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_llm_usage_called_at ON llm_usage(called_at);
            CREATE INDEX IF NOT EXISTS idx_llm_usage_category ON llm_usage(category);
            """
        )
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS study_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                week_label TEXT NOT NULL UNIQUE,
                generated_at TEXT NOT NULL,
                content_md TEXT NOT NULL,
                topics_covered TEXT,
                reminder_sent_tue INTEGER NOT NULL DEFAULT 0,
                reminder_sent_fri INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS cluster_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_at TEXT NOT NULL,
                post_count INTEGER NOT NULL DEFAULT 0,
                cluster_count INTEGER NOT NULL DEFAULT 0,
                unlabeled_count INTEGER NOT NULL DEFAULT 0,
                inertia REAL,
                silhouette_score REAL
            );
            """
        )
        # Phase 1: scoring columns on posts
        for stmt in [
            "ALTER TABLE posts ADD COLUMN signal_score REAL",
            "ALTER TABLE posts ADD COLUMN bucket TEXT",
            "ALTER TABLE posts ADD COLUMN project_matches TEXT",
            "ALTER TABLE posts ADD COLUMN interpretation TEXT",
        ]:
            try:
                connection.execute(stmt)
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
        # Phase 1: post_project_links — add inference tier and rationale columns
        for stmt in [
            "ALTER TABLE post_project_links ADD COLUMN tier TEXT",
            "ALTER TABLE post_project_links ADD COLUMN rationale TEXT",
        ]:
            try:
                connection.execute(stmt)
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
        # Phase 2: quality metrics for observability (created now, populated in Phase 2)
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS quality_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                week_label TEXT NOT NULL UNIQUE,
                computed_at TEXT NOT NULL,
                total_posts INTEGER NOT NULL DEFAULT 0,
                strong_count INTEGER NOT NULL DEFAULT 0,
                watch_count INTEGER NOT NULL DEFAULT 0,
                cultural_count INTEGER NOT NULL DEFAULT 0,
                noise_count INTEGER NOT NULL DEFAULT 0,
                avg_signal_score REAL,
                project_match_count INTEGER NOT NULL DEFAULT 0,
                output_word_count INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        connection.commit()

    LOGGER.info("Database migrations complete")
    return db_path


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    run_migrations()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
