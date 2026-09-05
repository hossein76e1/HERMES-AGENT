Hossein expects autonomous work: execute tasks without waiting for permission on each step. Work independently in background, give occasional status updates so he knows progress. Don't wait to be told to do obvious next steps. Respond in Persian when they write in Persian. Technical terms in English, translate unfamiliar ones in parentheses.
§
CSV DictWriter bug with AI extraction: when AI returns varying keys per item, collect ALL keys across all items first, then use extrasaction='ignore'. Pattern: `all_keys = set(); [all_keys.update(item.keys()) for item in items]; writer = csv.DictWriter(f, fieldnames=list(all_keys), extrasaction='ignore')`
§
Order bots lifecycle live: support_bot.py=@ShahbotSupportbot (8823286946) AI intake + outbox worker (customer msgs, 5s); survey_bot.py=@ShahbotSurveyBot (8681968795) admin panel + admin_inbox worker (admin notifications, 5s). Routing: customer-bound → outbox queue → sent by support bot; admin-bound (new order, receipts, direct msgs) → admin_inbox → sent by survey bot; receipt photos saved to receipts/ & re-sent by admin bot. Payment: ملت 6104-3379-4410-7284 حسین رضایی / USDT TRC20 TXk9Lm2pQvR7nJ4hKd8sWfY3aBcE5gUiZq (in order_flow.py). Chat binding in requirements JSON $.chat; statuses pending→quoted→awaiting_payment→payment_review→paid→in_progress→delivered. Tokens from state.db via restart_bots.sh; keeper cron 5m. Verify single instance after restart. E2E v3 passed.
§
Backup: 12h cron + file watcher for critical files. Restore: ~/.hermes/scripts/restore.sh. Projects backup separate.
§
File watcher: ~/.hermes/scripts/watch-backup.sh monitors config, secrets, state files. @reboot cron.
§
FastAPI ASGI module: always check which file has `app = FastAPI(...)` before running uvicorn. Project structure: main.py (models/DB) → api.py (endpoints/app). Command: `uvicorn api:app` not `uvicorn main:app`.
§
Disk monitor: cron 7150ce92fb65 runs every 6h, cleans pip/npm caches + __pycache__ if /data > 80%. Script: ~/.hermes/scripts/disk_monitor.sh. Log: ~/.hermes/logs/disk_monitor.log. Never deletes: .hermes, workspace, hermes-backup-repo, .config, .local. Current /data: 69% (290M).