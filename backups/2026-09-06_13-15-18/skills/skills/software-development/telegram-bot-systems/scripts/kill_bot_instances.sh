#!/usr/bin/env bash
# kill_bot_instances.sh — kill ALL running instances of given bot scripts, safely.
# Fixes the two classic traps:
#   1) orphan processes (ppid=1) that survive normal kills → cause Telegram 409 Conflict
#   2) the killer killing ITSELF (a bash -c scan whose cmdline contains the bot name)
# Usage: kill_bot_instances.sh support_bot.py survey_bot.py
set -u
SELF=$$
PATTERNS="$*"
if [ -z "$PATTERNS" ]; then
  echo "usage: $0 <bot.py> [more_bot.py ...]" >&2
  exit 1
fi

killed=0
for p in /proc/[0-9]*; do
  pid=${p#/proc/}
  [ "$pid" = "$SELF" ] && continue
  cmd=$(tr '\0' ' ' < "$p/cmdline" 2>/dev/null) || continue
  # only ever touch python processes running the named script — never shells
  case "$cmd" in
    python*)
      for pat in $PATTERNS; do
        case "$cmd" in
          *"$pat")
            kill -9 "$pid" 2>/dev/null && { echo "killed $pid: $cmd"; killed=$((killed+1)); }
            ;;
        esac
      done
      ;;
  esac
done

sleep 2
alive=0
for p in /proc/[0-9]*; do
  cmd=$(tr '\0' ' ' < "$p/cmdline" 2>/dev/null) || continue
  case "$cmd" in
    python*)
      for pat in $PATTERNS; do
        case "$cmd" in
          *"$pat") alive=$((alive+1)); echo "STILL ALIVE: ${p#/proc/} ($cmd)" ;;
        esac
      done
      ;;
  esac
done

if [ "$alive" -eq 0 ]; then
  echo "OK: no instances running ($killed killed)"
  exit 0
else
  echo "WARN: $alive instance(s) still alive — re-run or check keeper cron"
  exit 1
fi
