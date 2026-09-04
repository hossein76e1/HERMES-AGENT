Hossein expects autonomous work: execute tasks without waiting for permission on each step. Work independently in background, give occasional status updates so he knows progress. Don't wait to be told to do obvious next steps. Respond in Persian when they write in Persian. Technical terms in English, translate unfamiliar ones in parentheses.
§
CSV DictWriter bug with AI extraction: when AI returns varying keys per item, collect ALL keys across all items first, then use extrasaction='ignore'. Pattern: `all_keys = set(); [all_keys.update(item.keys()) for item in items]; writer = csv.DictWriter(f, fieldnames=list(all_keys), extrasaction='ignore')`
§
Smart order system complete (22/22 API tests): FastAPI backend, AI chat order collection, auto-pricing, JWT auth, SQLite, ZarinPal + card-to-card payment, admin panel. GitHub: hossein76e1/HERMES-AGENT (de4e248, be83456). Cloudflare tunnel temporary — need custom domain or VPS firewall changes for permanent access.
§
Backup system: 12-hour cron (ID: 09bc94629578) + file watcher (inotifywait) for immediate backup on critical file changes. GitHub push protection resolved by filtering state.db from git history. Sensitive files excluded from pushes.
§
File watcher: /data/.hermes/scripts/watch-backup.sh monitors config.yaml, SOUL.md, .env, auth.json, state.db, kanban.db, memories/, sessions/, cron/ — triggers backup with 30s debounce. Runs as background proc with @reboot cron.
§
User wants disaster recovery: restore Hermes on new VPS from GitHub backup (hossein76e1/HERMES-AGENT). Needs restore.sh script.
§
User wants project code backup (Telegram bots, workspace projects) — separate from Hermes config backup. Needs backup_projects.sh with own cron.
§
GitHub PAT can be shared in this private chat for backup script fix.
§
Prefers autonomous execution with brief Persian status updates. Says 'دارم روش کار میکنم' not 'دارم شروع میکنم'. Frustrated when I say I'll start but don't actually do the work.