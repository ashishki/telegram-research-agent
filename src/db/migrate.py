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
        connection.commit()

    LOGGER.info("Database migrations complete")
    return db_path


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    run_migrations()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
