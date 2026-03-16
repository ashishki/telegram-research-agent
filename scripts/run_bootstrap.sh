#!/usr/bin/env bash

set -euo pipefail

set -a
. /srv/openclaw-you/.env
set +a

export PYTHONPATH="/srv/openclaw-you/workspace/telegram-research-agent/src"

python3 /srv/openclaw-you/workspace/telegram-research-agent/src/main.py bootstrap
