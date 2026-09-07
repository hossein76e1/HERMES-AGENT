#!/bin/bash
# WhatsApp Assistant — Start script
# Usage: bash start.sh (foreground) or nohup bash start.sh & (background)

cd "$(dirname "$0")"

# Load API keys from hermes .env
set -a
source /data/.hermes/.env
set +a

export AI_MODEL="${AI_MODEL:-glm-5.3-flash}"

echo "[WhatsApp Assistant] Starting..."
exec node index.js
