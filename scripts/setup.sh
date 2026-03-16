#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/srv/openclaw-you/workspace/telegram-research-agent"
ENV_FILE="/srv/openclaw-you/.env"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  source "$ENV_FILE"
  set +a
else
  echo "Warning: $ENV_FILE not found. Continuing with current environment."
fi

cd "$PROJECT_ROOT"
python3 src/db/migrate.py

cat <<'EOF'

Database scaffold is ready.

Phase 2 Telethon interactive auth will require:
1. Export or source TELEGRAM_SESSION_PATH before running ingestion setup.
2. Run the future bootstrap/auth flow in an interactive shell.
3. Complete the phone number / login code prompts when Telethon requests them.

No Telegram session was created by this script.
EOF
