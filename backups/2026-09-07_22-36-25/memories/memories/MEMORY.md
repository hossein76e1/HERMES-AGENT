Hossein expects autonomous work: execute tasks without waiting for permission on each step. Work independently in background, give occasional status updates so he knows progress. Don't wait to be told to do obvious next steps. Respond in Persian when they write in Persian. Technical terms in English, translate unfamiliar ones in parentheses.
§
Restart: kill ALL /proc matches FIRST (orphans→409); keeper 2s sleep can double-start → wait 5s+verify after kill. BOTS MUST RUN WITH /usr/local/bin/python3 (has apscheduler → PTB JobQueue); /opt/venv python3 has NO apscheduler → job_queue=None → poll_new_orders/admin_inbox_worker/outbox_worker all silently dead (admin never notified!). Keeper fixed to use PYTHON=/usr/local/bin/python3.
§
Hossein retracted a mass project deletion once («پشیمون شدم») — confirm destructive deletions before executing. Inventory: order system (support_bot.py, order_flow.py, auto_builder.py, order-system/) + smart-scraper.
§
File watcher: ~/.hermes/scripts/watch-backup.sh, @reboot cron. FastAPI: check which file has `app = FastAPI(...)` before uvicorn — usually `uvicorn api:app` not main:app.
§
Disk monitor: cronjob 3238f8dd6c13 every 30m; if /data > 80% cleans caches + prunes backup repo (keep 3 local dirs); if still >80% after cleanup → warn Hossein, never delete essentials without asking. Backups ONLY on GitHub (hossein76e1/HERMES-AGENT), keep 3 dirs locally.
§
Prompt caching WORKS on 9router/GLM (~52% cached, verified). Rules: byte-identical system prompt prefix; ai_faq stable window fixed. bots_keeper.sh: exact cmdline match 'python3 <script>' (grep self-match bug → never restarted). TeamoRouter 503 insufficient-balance intermittently → retry loops essential.
§
WhatsApp bot: projects/whatsapp_assistant (baileys, model 'GLM' @9router) on Hossein's own number 09200919019; self-chat (Message yourself) works; tasks/reminders/shopping per-user scoped by jid; 1 AI call per message ~14s (9router thinking latency, not code); restart = node index.js with .env sourced, auth/ persists (no QR); QR image → wa_login_qr.png; data.json + 6h backups.