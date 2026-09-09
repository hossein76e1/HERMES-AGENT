Hossein expects autonomous work: execute tasks without waiting for permission on each step. Work independently in background, give occasional status updates so he knows progress. Don't wait to be told to do obvious next steps. Respond in Persian when they write in Persian. Technical terms in English, translate unfamiliar ones in parentheses.
§
Restart: kill ALL /proc matches first (orphans→409), wait 5s. Bots MUST run with /usr/local/bin/python3 (apscheduler for PTB JobQueue; /opt/venv lacks it → silent dead inbox/outbox). Keeper uses /usr/local/bin/python3.
§
Hossein retracted a mass deletion once («پشیمون شدم») — confirm destructive deletions before executing. Inventory: order system (support_bot.py, order_flow.py, survey_bot.py, order-system/) + telegram_assistant.
§
Cron: system crontab dead in container. Hermes cron create BLOCKS process-launching scripts (#30719) — piggyback watchdogs onto approved disk_monitor.sh (runs every 5m). Security: 2026-09-08 Hossein pasted brokerage creds in chat (pw changed, msg deleted); warn never to paste financial creds in chat; redact via SQL REPLACE in state.db.
§
Disk monitor: Hermes cronjob 3238f8dd6c13 every 5m; /data >80% → clean caches + prune backup repo (keep 3 local dirs); still >80% → warn Hossein, never delete essentials. Backups ONLY GitHub (hossein76e1/HERMES-AGENT).
§
Prompt caching WORKS on 9router/GLM (~52%). Byte-identical system prompt prefix. 9router 503/429 intermittent → retry loops essential. AI-down message: '⚠️ سرویس هوش مصنوعی در دسترس نیست'.
§
Telegram assistant @Hosseinagentcoderbot (projects/telegram_assistant/) = reminder bot. Token TELEGRAM_ASSISTANT_TOKEN in /data/.hermes/.env. PTB/openai/apscheduler installed in /usr/local/bin/python3. Guarded by bots_keeper_once.sh 5m. Start ONLY via bots_launcher.sh (PPid=1); terminal/nohup launches DIE at session end (down 2x). Reminders/shopping no AI (JobQueue +03:30); chat via GLM. survey /msg → admin no AI.
§
User prefs: simple Q → fast short answer, no tool chains; deep work → full detail. Never silently drop — explicit failure messages wanted. Security-conscious: never store secrets in chat/memory; if leaked → revoke + redact state.db.