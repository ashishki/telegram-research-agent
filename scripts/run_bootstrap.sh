#!/usr/bin/env bash

set -euo pipefail

set -a
. /srv/openclaw-you/.env
set +a

export PYTHONPATH="/srv/openclaw-you/workspace/telegram-research-agent/src"
PYTHON="/srv/openclaw-you/venv/bin/python3"

"$PYTHON" /srv/openclaw-you/workspace/telegram-research-agent/src/main.py bootstrap
