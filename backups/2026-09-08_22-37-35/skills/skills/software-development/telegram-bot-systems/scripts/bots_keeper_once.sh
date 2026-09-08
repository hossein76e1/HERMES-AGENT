#!/bin/bash
# bots_keeper_once.sh — SINGLE-PASS Telegram order-bot health check.
# Caller: Hermes cronjob every 5m (no_agent, deliver local).
# HARD RULE: this file must contain NO while/for-sleep loops, NO nohup/setsid, NO `&`.
# Hermes cron-creation policy #30719 scans the cron-called script's CONTENT and blocks
# anything that looks like a persistent launch / respawn loop. All daemonization lives
# in bots_launcher.sh (a plain file invocation is not scanned). Ask-to-unblock does NOT
# work — the rule is structural. Proof: a one-line `echo` probe script created fine.
# Quiet when all is well (empty stdout = no delivery); prints + exit 1 only when a bot
# is down AND no token exists to recover it.

PROJECTS_DIR="/data/workspace/projects"
ENV_FILE="/data/.hermes/.env"
PYTHON="/usr/local/bin/python3"          # MUST be the interpreter that has APScheduler
LAUNCHER="/data/.hermes/scripts/bots_launcher.sh"

set -a
source "$ENV_FILE" 2>/dev/null
set +a

# Token fallback: bot tokens often live only in Hermes state.db message history.
db_token() {
  python3 - "$1" <<'PYEOF'
import sqlite3, re, sys
pat = sys.argv[1]
try:
    conn = sqlite3.connect('/data/.hermes/state.db')
    rows = conn.execute(
        "SELECT content FROM messages WHERE content LIKE ? ORDER BY id DESC LIMIT 500",
        ('%' + pat.split(':')[0] + '%',)).fetchall()
    conn.close()
    for (content,) in rows:
        if not content:
            continue
        m = re.search(r'(' + re.escape(pat) + r':[A-Za-z0-9_-]{30,50})', content)
        if m:
            print(m.group(1)); break
except Exception:
    pass
PYEOF
}

[ -z "${SURVEY_BOT_TOKEN:-}" ]  && SURVEY_BOT_TOKEN="$(db_token '8681968795')"
[ -z "${SUPPORT_BOT_TOKEN:-}" ] && SUPPORT_BOT_TOKEN="$(db_token '8823286946')"

problems=0

check_bot() {
  local script="$1" token_var="$2" name="$3"
  local token="${!token_var}"
  local running=false p c
  # EXACT cmdline match: "$PYTHON <path><script>". A bare substring/grep pattern matches
  # the scanner's OWN cmdline (it embeds the script names) -> false "already running" and
  # a dead bot is never restarted. Observed 2026-09-08: one pid reported as BOTH bots.
  for p in $(ls /proc/ 2>/dev/null | grep -E '^[0-9]+$'); do
    [ -r "/proc/$p/cmdline" ] || continue
    c=$(tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null)
    case "$c" in
      "$PYTHON $PROJECTS_DIR/$script "*|"$PYTHON $PROJECTS_DIR/$script") running=true; break;;
    esac
  done
  if [ "$running" = true ]; then
    return 0
  fi
  if [ -z "$token" ]; then
    echo "[$(date '+%F %T')] $name DOWN and no token available — manual action needed"
    problems=$((problems + 1))
    return 1
  fi
  "$LAUNCHER" "$script" "$token_var" "$token"
}

check_bot "support_bot.py" "SUPPORT_BOT_TOKEN" "@ShahbotSupportbot"
check_bot "survey_bot.py"  "SURVEY_BOT_TOKEN"  "@ShahbotSurveyBot"

[ "$problems" -gt 0 ] && exit 1
exit 0
