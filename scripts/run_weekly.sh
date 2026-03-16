#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/srv/openclaw-you/workspace/telegram-research-agent"

set -a
source /srv/openclaw-you/.env
set +a

export PYTHONPATH="${PROJECT_ROOT}"

start_ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo "weekly pipeline start=${start_ts}"

if python3 "${PROJECT_ROOT}/src/main.py" ingest; then
  exit_code=0
else
  exit_code=$?
fi

echo "weekly pipeline exit_code=${exit_code}"
exit "${exit_code}"
