#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/srv/openclaw-you/workspace/telegram-research-agent"
ENV_FILE="/srv/openclaw-you/.env"
DEFAULT_DB_PATH="$PROJECT_ROOT/data/agent.db"
DEFAULT_SESSION_PATH="/srv/openclaw-you/secrets/telegram.session"
INGESTION_STALE_DAYS=8

if [[ -f "$ENV_FILE" ]]; then
  set -a
  source "$ENV_FILE"
  set +a
fi

DB_PATH="${AGENT_DB_PATH:-$DEFAULT_DB_PATH}"
SESSION_PATH="${TELEGRAM_SESSION_PATH:-$DEFAULT_SESSION_PATH}"
export DB_PATH
export INGESTION_STALE_DAYS

if [[ ! -f "$DB_PATH" ]]; then
  echo "Healthcheck failed: database file not found at $DB_PATH" >&2
  exit 1
fi

if [[ ! -r "$DB_PATH" ]]; then
  echo "Healthcheck failed: database file is not readable at $DB_PATH" >&2
  exit 1
fi

if [[ -z "${LLM_API_KEY:-}" ]]; then
  echo "Healthcheck failed: LLM_API_KEY is not set" >&2
  exit 1
fi

if [[ ! -f "$SESSION_PATH" ]]; then
  echo "Healthcheck failed: Telegram session file not found at $SESSION_PATH" >&2
  exit 1
fi

if [[ ! -r "$SESSION_PATH" ]]; then
  echo "Healthcheck failed: Telegram session file is not readable at $SESSION_PATH" >&2
  exit 1
fi

PYTHON="/srv/openclaw-you/venv/bin/python3"

db_check_output="$("$PYTHON" -c '
import os
import sqlite3
import sys

db_path = os.environ["DB_PATH"]
connection = sqlite3.connect(db_path)
try:
    count = connection.execute("SELECT COUNT(*) FROM raw_posts").fetchone()[0]
except sqlite3.Error as exc:
    print(f"Healthcheck failed: database query failed: {exc}", file=sys.stderr)
    raise SystemExit(1)
finally:
    connection.close()
print(count)
')"

if [[ -z "$db_check_output" ]]; then
  echo "Healthcheck failed: unable to query raw_posts" >&2
  exit 1
fi

last_ingested_at="$("$PYTHON" -c '
import os
import sqlite3
import sys
from datetime import datetime, timezone, timedelta

db_path = os.environ["DB_PATH"]
connection = sqlite3.connect(db_path)
try:
    row = connection.execute("SELECT MAX(ingested_at) FROM raw_posts").fetchone()
except sqlite3.Error as exc:
    print(f"Healthcheck failed: ingestion freshness query failed: {exc}", file=sys.stderr)
    raise SystemExit(1)
finally:
    connection.close()

value = row[0] if row else None
if not value:
    print("WARN: no ingested_at values found in raw_posts", file=sys.stderr)
    raise SystemExit(0)

parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
if parsed.tzinfo is None:
    parsed = parsed.replace(tzinfo=timezone.utc)
else:
    parsed = parsed.astimezone(timezone.utc)

if parsed < datetime.now(timezone.utc) - timedelta(days=int(os.environ["INGESTION_STALE_DAYS"])):
    print(f"WARN: last ingestion is stale last_ingested_at={parsed.isoformat()}", file=sys.stderr)
' 2>&1)"

if [[ -n "$last_ingested_at" ]]; then
  echo "$last_ingested_at" >&2
fi

echo "Healthcheck OK"
