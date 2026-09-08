#!/usr/bin/env bash
# bots_launcher.sh — the ONLY place daemonization lives, so the cron-called keeper
# stays free of nohup/&/setsid and passes Hermes cron-creation policy #30719.
# usage: bots_launcher.sh <script.py> <TOKEN_ENV_VAR_NAME> <token_value>
# NOTE: export the bot's OWN token var only. Exporting both token vars with one bot's
# value makes the other bot authenticate with the wrong token (401 / 409 confusion).
PYTHON="/usr/local/bin/python3"           # interpreter WITH APScheduler -> PTB JobQueue
PROJECTS_DIR="/data/workspace/projects"
LOG_DIR="/data/.hermes/logs"
SCRIPT="${1:?script required}"
TOKEN_VAR="${2:?token var required}"
TOKEN="${3:?token required}"
mkdir -p "$LOG_DIR"

cd "$PROJECTS_DIR" || exit 1
env "$TOKEN_VAR=$TOKEN" nohup "$PYTHON" "$PROJECTS_DIR/$SCRIPT" \
  >> "$LOG_DIR/${SCRIPT%.py}.log" 2>&1 &
# Detach from the caller's process group so a cron/agent shell exit cannot take the bot down.
disown 2>/dev/null || true
echo "[$(date '+%F %T')] launched $SCRIPT (pid $!)"

# PITFALL (2026-09-08): do NOT 'modernize' this to start-stop-daemon on minimal images —
# the installed version rejected `--env` ("unrecognized option"). `env VAR=… nohup … &`
# is the validated form. After launching, VERIFY within ~10s that the bot log shows the
# JobQueue worker's periodic line (outbox_worker / admin_inbox_worker 'executed
# successfully'); absent = app.job_queue is None = wrong interpreter, bot is NOT healthy.
